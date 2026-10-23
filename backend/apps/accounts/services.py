import csv
import io

from django.db import transaction

from apps.academics.models import AcademicYear, SchoolClass, Section
from apps.core.utils import random_password

from .models import StudentProfile, User

IMPORT_COLUMNS = ["roll_no", "name", "class", "section"]
MAX_IMPORT_ROWS = 2000


class ImportError_(ValueError):
    def __init__(self, errors):
        super().__init__("Import failed")
        self.errors = errors


def _read_csv(uploaded):
    raw = uploaded.read()
    if len(raw) > 2 * 1024 * 1024:
        raise ImportError_([{"row": 0, "error": "File is larger than 2 MB."}])
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportError_([{"row": 0, "error": "File must be UTF-8 encoded CSV."}]) from None
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in IMPORT_COLUMNS if c not in headers]
    if missing:
        raise ImportError_([{"row": 0, "error": f"Missing columns: {', '.join(missing)}"}])
    reader.fieldnames = headers
    rows = list(reader)
    if len(rows) > MAX_IMPORT_ROWS:
        raise ImportError_([{"row": 0, "error": f"At most {MAX_IMPORT_ROWS} rows per import."}])
    return rows


def import_students(uploaded):
    """Validate the whole file first; create nothing unless every row is valid.

    Returns (created rows with their one-time passwords, labels of sections that were created).
    """
    year = AcademicYear.current()
    if year is None:
        raise ImportError_([{"row": 0, "error": "No current academic year is configured."}])
    rows = _read_csv(uploaded)
    classes = {c.grade: c for c in SchoolClass.objects.all()}
    existing_rolls = {r.lower() for r in StudentProfile.objects.filter(academic_year=year).values_list("roll_no", flat=True)}
    existing_users = {u.lower() for u in User.objects.values_list("username", flat=True)}

    errors, clean, seen = [], [], set()
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        roll = (row.get("roll_no") or "").strip()
        name = (row.get("name") or "").strip()
        section_name = (row.get("section") or "").strip().upper()
        try:
            grade = int((row.get("class") or "").strip())
        except ValueError:
            grade = None
        problems = []
        if not roll or not roll.replace("-", "").replace("_", "").isalnum() or len(roll) > 32:
            problems.append("invalid roll_no")
        elif roll.lower() in seen:
            problems.append("duplicate roll_no in file")
        elif roll.lower() in existing_rolls or roll.lower() in existing_users:
            problems.append("roll_no already exists")
        if not name or len(name) > 128:
            problems.append("invalid name")
        if grade not in classes:
            problems.append("class must be an existing grade 1-12")
        if not section_name.isalpha() or len(section_name) > 8:
            problems.append("invalid section")
        if problems:
            errors.append({"row": i, "error": "; ".join(problems)})
            continue
        seen.add(roll.lower())
        clean.append(
            {
                "roll_no": roll,
                "name": name,
                "grade": grade,
                "section": section_name,
                "guardian_phone": (row.get("guardian_phone") or "").strip()[:20],
            }
        )
    if errors:
        raise ImportError_(errors)

    created, created_sections = [], []
    with transaction.atomic():
        sections = {}
        for item in clean:
            key = (item["grade"], item["section"])
            if key not in sections:
                section, was_created = Section.objects.get_or_create(school_class=classes[item["grade"]], name=item["section"])
                sections[key] = section
                if was_created:
                    created_sections.append(section.label)
        for item in clean:
            password = random_password()
            section = sections[(item["grade"], item["section"])]
            user = User(username=item["roll_no"], full_name=item["name"], role=User.Role.STUDENT, must_change_password=True)
            user.set_password(password)
            user.save()
            StudentProfile.objects.create(
                user=user,
                academic_year=year,
                roll_no=item["roll_no"],
                school_class=section.school_class,
                section=section,
                guardian_phone=item["guardian_phone"],
            )
            created.append({"id": user.pk, "roll_no": item["roll_no"], "name": item["name"], "section": section.label, "password": password})
    return created, created_sections


@transaction.atomic
def promote_students(new_year_label):
    """Year-end promotion: everyone moves up one class; class 12 students graduate (deactivated, kept for history)."""
    current = AcademicYear.objects.select_for_update().filter(is_current=True).first()
    if current is None:
        raise ValueError("No current academic year is configured.")
    if AcademicYear.objects.filter(label=new_year_label).exists():
        raise ValueError("That academic year already exists.")
    current.is_current = False
    current.save(update_fields=["is_current"])
    new_year = AcademicYear.objects.create(label=new_year_label, is_current=True)

    classes = {c.grade: c for c in SchoolClass.objects.all()}
    profiles = StudentProfile.objects.select_related("user", "school_class", "section").filter(
        academic_year=current, user__is_active=True
    )
    promoted = graduated = 0
    section_cache = {}
    for profile in profiles:
        grade = profile.school_class.grade
        if grade >= 12 or (grade + 1) not in classes:
            user = profile.user
            user.is_active = False
            user.save(update_fields=["is_active"])
            user.bump_token_version()
            graduated += 1
            continue
        key = (grade + 1, profile.section.name)
        if key not in section_cache:
            section_cache[key], _ = Section.objects.get_or_create(school_class=classes[grade + 1], name=profile.section.name)
        profile.school_class = classes[grade + 1]
        profile.section = section_cache[key]
        profile.academic_year = new_year
        profile.save(update_fields=["school_class", "section", "academic_year"])
        promoted += 1
    return {"from_year": current.label, "to_year": new_year.label, "promoted": promoted, "graduated": graduated}
