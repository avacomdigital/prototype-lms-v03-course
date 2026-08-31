import django.db.models.deletion
from django.db import migrations, models
import exams.models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Exam",
            fields=[
                ("id", models.CharField(default=exams.models.new_document_id, editable=False, max_length=24, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=250)),
                ("status", models.CharField(choices=[("draft", "Borrador"), ("active", "Activo"), ("finished", "Finalizado")], default="draft", max_length=16)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ], options={"db_table": "exams"},
        ),
        migrations.CreateModel(
            name="Student",
            fields=[
                ("id", models.BigIntegerField(editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=250)),
                ("device_id", models.CharField(blank=True, db_index=True, max_length=120)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ], options={"db_table": "students", "ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="Question",
            fields=[
                ("id", models.CharField(default=exams.models.new_document_id, editable=False, max_length=24, primary_key=True, serialize=False)),
                ("text", models.CharField(max_length=600)),
                ("position", models.PositiveSmallIntegerField()),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="exams.exam")),
            ], options={"db_table": "questions", "ordering": ["position"]},
        ),
        migrations.CreateModel(
            name="AnswerOption",
            fields=[
                ("id", models.CharField(default=exams.models.new_document_id, editable=False, max_length=24, primary_key=True, serialize=False)),
                ("text", models.CharField(max_length=400)),
                ("position", models.PositiveSmallIntegerField()),
                ("is_correct", models.BooleanField(default=False)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="exams.question")),
            ], options={"db_table": "answer_options", "ordering": ["position"]},
        ),
        migrations.CreateModel(
            name="Submission",
            fields=[
                ("id", models.CharField(default=exams.models.new_document_id, editable=False, max_length=24, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("in_progress", "En progreso"), ("finished", "Finalizado")], default="in_progress", max_length=16)),
                ("score", models.PositiveSmallIntegerField(default=0)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("exam", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="submissions", to="exams.exam")),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="submissions", to="exams.student")),
            ], options={"db_table": "submissions"},
        ),
        migrations.CreateModel(
            name="StudentAnswer",
            fields=[
                ("id", models.CharField(default=exams.models.new_document_id, editable=False, max_length=24, primary_key=True, serialize=False)),
                ("answered_at", models.DateTimeField(auto_now=True)),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_answers", to="exams.question")),
                ("selected_option", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="student_answers", to="exams.answeroption")),
                ("submission", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="answers", to="exams.submission")),
            ], options={"db_table": "student_answers"},
        ),
        migrations.AddConstraint(model_name="question", constraint=models.UniqueConstraint(fields=("exam", "position"), name="unique_question_position")),
        migrations.AddConstraint(model_name="answeroption", constraint=models.UniqueConstraint(fields=("question", "position"), name="unique_option_position")),
        migrations.AddConstraint(model_name="submission", constraint=models.UniqueConstraint(fields=("student", "exam"), name="unique_student_exam")),
        migrations.AddConstraint(model_name="studentanswer", constraint=models.UniqueConstraint(fields=("submission", "question"), name="unique_submission_question")),
    ]
