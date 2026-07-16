from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery("loginvestigator", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", accept_content=["json"], result_serializer="json")
celery_app.conf.beat_schedule = {
    "mark-stuck-jobs-every-minute": {"task": "mark_stuck_jobs", "schedule": 60.0},
    "verify-evidence-periodically": {"task": "verify_evidence_files", "schedule": get_settings().integrity_check_interval_seconds},
}
celery_app.autodiscover_tasks(["app"])
