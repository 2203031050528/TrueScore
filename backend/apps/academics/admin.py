from django.contrib import admin

from .models import AcademicYear, Chapter, SchoolClass, Section, Subject

admin.site.register(AcademicYear)
admin.site.register(SchoolClass)
admin.site.register(Section)
admin.site.register(Subject)
admin.site.register(Chapter)
