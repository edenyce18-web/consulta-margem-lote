from celery import Celery
from app.config import settings

celery_app = Celery(
    "consulta_margem",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Manaus",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                   # Só confirma após conclusão
    worker_prefetch_multiplier=1,          # Um task por worker por vez
    # Sem time limit global — processar_lote pode ter milhares de CPFs.
    # O timeout por CPF é controlado pelos timeouts do Playwright (base_adapter.py).
    # task_soft_time_limit e task_time_limit são definidos por tarefa se necessário.
    result_expires=86400,                  # Resultados no Redis por 24h
    task_routes={
        "app.tasks.processar_lote": {"queue": "celery"},
    },
)
