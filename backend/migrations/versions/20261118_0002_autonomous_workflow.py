"""Add discovery freshness, resume versions, eligibility, and automation audit tables."""
from alembic import op
import sqlalchemy as sa

revision = "20261118_0002"
down_revision = "20261118_0001"
branch_labels = None
depends_on = None


def upgrade():
    jobs = [
        sa.Column("discovered_at", sa.Text()), sa.Column("expires_at", sa.Text()), sa.Column("expired", sa.Boolean()),
        sa.Column("external_id", sa.Text()), sa.Column("canonical_url", sa.Text()), sa.Column("employment_type", sa.Text()),
        sa.Column("salary_min", sa.Float()), sa.Column("salary_max", sa.Float()), sa.Column("salary_currency", sa.String(12)),
        sa.Column("experience_min", sa.Float()), sa.Column("experience_max", sa.Float()), sa.Column("match_score", sa.Integer()),
        sa.Column("eligibility_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("eligibility_reasons", sa.Text(), nullable=False, server_default="[]"), sa.Column("last_checked_at", sa.Text()),
    ]
    for column in jobs:
        op.add_column("jobs", column)
    op.execute("UPDATE jobs SET discovered_at = created_at WHERE discovered_at IS NULL")

    applications = [
        sa.Column("normalized_job_url", sa.Text()), sa.Column("company_key", sa.Text()), sa.Column("job_key", sa.Text()),
        sa.Column("resume_version_id", sa.Integer(), sa.ForeignKey("resume_versions.id", ondelete="SET NULL")),
        sa.Column("application_date", sa.Text()),
        sa.Column("submission_status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("confirmation_details", sa.Text(), nullable=False, server_default=""),
        sa.Column("failure_reason", sa.Text(), nullable=False, server_default=""), sa.Column("last_activity_at", sa.Text()),
    ]
    # resume_versions is created before the FK is added below.
    applications[3] = sa.Column("resume_version_id", sa.Integer())
    for column in applications:
        op.add_column("applications", column)

    op.create_table(
        "resume_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False), sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("candidate_id", "file_path", name="uq_resume_version_candidate_path"),
    )
    op.create_foreign_key("fk_applications_resume_version", "applications", "resume_versions", ["resume_version_id"], ["id"], ondelete="SET NULL")
    op.create_index("ux_app_candidate_normalized_url", "applications", ["candidate_id", "normalized_job_url"], unique=True,
                    postgresql_where=sa.text("normalized_job_url IS NOT NULL AND normalized_job_url <> ''"))
    op.create_index("ux_app_candidate_company_job", "applications", ["candidate_id", "company_key", "job_key"], unique=True,
                    postgresql_where=sa.text("company_key IS NOT NULL AND company_key <> '' AND job_key IS NOT NULL AND job_key <> ''"))

    op.create_table(
        "source_health", sa.Column("source", sa.String(120), primary_key=True), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False), sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_status", sa.Integer()), sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "automation_configs", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submissions_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_time", sa.String(5), nullable=False, server_default="09:00"), sa.Column("timezone", sa.String(80), nullable=False, server_default="UTC"),
        sa.Column("last_scheduled_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "automation_runs", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"), sa.Column("stop_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "automation_queue", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE")), sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_automation_queue_pending", "automation_queue", ["status", "available_at", "id"])
    op.create_index("ux_automation_queue_active_candidate_job", "automation_queue", ["candidate_id", "job_id", "task_type"], unique=True,
                    postgresql_where=sa.text("job_id IS NOT NULL AND status IN ('queued','processing')"))
    op.create_table(
        "automation_events", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("automation_runs.id", ondelete="SET NULL")),
        sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="SET NULL")), sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_automation_events_candidate_created", "automation_events", ["candidate_id", "created_at"])


def downgrade():
    for table in ("automation_events", "automation_queue", "automation_runs", "automation_configs", "source_health"):
        op.drop_table(table)
    op.drop_index("ux_app_candidate_company_job", table_name="applications")
    op.drop_index("ux_app_candidate_normalized_url", table_name="applications")
    op.drop_constraint("fk_applications_resume_version", "applications", type_="foreignkey")
    for column in ("last_activity_at", "failure_reason", "confirmation_details", "submission_status", "application_date", "job_key", "company_key", "normalized_job_url", "resume_version_id"):
        op.drop_column("applications", column)
    op.drop_table("resume_versions")
    for column in ("last_checked_at", "eligibility_reasons", "eligibility_status", "match_score", "experience_max", "experience_min", "salary_currency", "salary_max", "salary_min", "employment_type", "canonical_url", "external_id", "expired", "expires_at", "discovered_at"):
        op.drop_column("jobs", column)
