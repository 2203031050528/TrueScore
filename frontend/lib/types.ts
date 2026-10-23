export type Role = "admin" | "teacher" | "student";

export interface Me {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  must_change_password: boolean;
  profile: null | {
    roll_no: string;
    class_id: number;
    grade: number;
    section_id: number;
    section: string;
    section_label: string;
    academic_year: string;
    guardian_phone: string;
    simple_mode: boolean;
  };
}

export interface Chapter { id: number; subject: number; name: string; order: number }
export interface Subject { id: number; school_class: number; grade: number; name: string; chapters: Chapter[] }
export interface Section { id: number; school_class: number; name: string; label: string; student_count?: number }
export interface SchoolClass { id: number; grade: number; simple_mode: boolean; sections: Section[]; subjects: { id: number; name: string }[] }

export interface VideoProgress { last_position_s: number; seconds_watched: number; percent: number; completed: boolean }
export interface StudentVideo {
  id: number; chapter: number; chapter_name: string; subject_id: number; subject_name: string;
  title: string; description: string; duration_s: number; order: number; progress: VideoProgress;
}
export interface AdminVideo {
  id: number; chapter: number; chapter_name: string; subject_id: number; subject_name: string; grade: number;
  title: string; description: string; r2_key: string; duration_s: number; thumbnail_key: string;
  status: "draft" | "published"; order: number; created_at: string;
}

export type QuestionType = "mcq_single" | "mcq_multi" | "true_false" | "numeric" | "short_answer";
export type Difficulty = "easy" | "medium" | "hard";

export interface UpcomingExam {
  id: number; title: string; subject: string; start_at: string; end_at: string; duration_min: number; total_marks: string;
  status: "upcoming" | "live" | "closed" | "graded" | "published"; needs_access_code: boolean; require_fullscreen: boolean;
  instructions: string; attempt: null | { id: number; status: "in_progress" | "submitted"; submitted_at: string | null };
}

export interface PaperQuestion {
  number: number; id: number; part: string; part_instructions: string; type: QuestionType; text: string;
  image_url: string | null; marks: string; negative_marks: string; options: { id: string; text: string }[];
  answer: null | { options?: string[]; value?: string; text?: string }; flagged: boolean;
}

export interface AttemptState {
  attempt_id: number; status: "in_progress" | "submitted"; submit_reason: string; server_time: string;
  started_at: string; deadline_at: string; submitted_at: string | null;
  exam: { id: number; title: string; subject: string; instructions: string; duration_min: number; total_marks: string; require_fullscreen: boolean; max_fullscreen_exits: number };
  fullscreen_exits: number; watermark: string; simple_mode: boolean; questions?: PaperQuestion[];
}

export interface ResultSummary {
  exam_id: number; title: string; subject: string; date: string; score: string; max_score: string; percentage: number;
  passed: boolean; pass_marks: string; rank: number | null; section_size: number; published_at: string; show_answers: boolean;
}
export interface ReviewQuestion {
  number: number; question_id: number; part: string; type: QuestionType; text: string; image_url: string | null; marks: string;
  options: { text: string; chosen: boolean; is_correct?: boolean }[]; your_answer: null | { value?: string; text?: string };
  answered: boolean; is_correct: boolean | null; marks_awarded: string | null; explanation?: string; correct_value?: string; tolerance?: string;
}
export interface ResultDetail extends ResultSummary { questions: ReviewQuestion[] | null }

export interface Progress {
  student: { name: string; roll_no: string; section: string; grade: number };
  subjects: { subject_id: number; subject: string; videos: number; completed: number; percent: number }[];
  continue_watching: { video_id: number; title: string; subject: string; last_position_s: number; duration_s: number }[];
  upcoming_exams: { id: number; title: string; subject: string; start_at: string; end_at: string; status: string }[];
  latest_results: ResultSummary[];
  score_trend: { exam_id: number; title: string; date: string; percentage: number }[];
  weak_chapters: { chapter_id: number; chapter: string; percentage: number }[];
  rank: null | { exam: string; rank: number | null; section_size: number };
}

export interface QuestionOption { id?: number; text: string; is_correct: boolean; order?: number }
export interface Question {
  id: number; subject: number; subject_name: string; grade: number; chapter: number; chapter_name: string; type: QuestionType;
  text: string; image_key: string; image_url: string | null; difficulty: Difficulty; marks: string; negative_marks: string;
  explanation: string; numeric_answer: string | null; numeric_tolerance: string; is_active: boolean; version: number;
  parent: number | null; options: QuestionOption[]; locked: boolean; created_at: string;
}

export interface ExamPartRule { easy: number; medium: number; hard: number; chapters: number[]; per_student: boolean; marks?: Partial<Record<Difficulty, number>> }
export interface ExamPart { id: number; exam: number; name: string; order: number; instructions: string; rule: ExamPartRule; question_count: number }
export interface ExamSettings {
  shuffle_questions: boolean; shuffle_options: boolean; require_fullscreen: boolean; max_fullscreen_exits: number;
  access_code: string; ip_allowlist: string[]; require_seb: boolean; seb_config_key: string; show_answers: boolean;
}
export interface Exam {
  id: number; title: string; school_class: number; grade: number; subject: number; subject_name: string; instructions: string;
  start_at: string; end_at: string; duration_min: number; total_marks: string; pass_marks: string;
  status: "draft" | "scheduled" | "graded" | "published"; effective_status: string; settings: ExamSettings;
  section_ids: number[]; sections_label: string[]; parts: ExamPart[]; attempt_count: number;
  scheduled_at: string | null; published_at: string | null; created_at: string;
}
export interface ExamQuestion { id: number; exam: number; part: number; question: number; order: number; marks: string; question_detail: Question }

export interface Student {
  id: number; username: string; full_name: string; is_active: boolean; must_change_password: boolean; last_login: string | null;
  roll_no: string; class_id: number; grade: number; section_id: number; section_label: string; guardian_phone: string; academic_year: string;
}

export interface MonitorRow {
  student_id: number; roll_no: string; name: string; section: string; state: "not_started" | "in_progress" | "disconnected" | "submitted";
  attempt_id: number | null; started_at: string | null; deadline_at: string | null; submitted_at: string | null; submit_reason: string;
  last_seen_at: string | null; answered: number; total_questions: number | null; flag_count: number; fullscreen_exits: number; ip: string | null;
}

export interface AuditEntry { id: number; actor_username: string | null; action: string; entity: string; entity_id: string; before: unknown; after: unknown; reason: string; ip: string | null; at: string }

export type { Paginated } from "./api";
