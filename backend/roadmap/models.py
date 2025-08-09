# roadmaps/models.py
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.conf import settings


# ---------------------------
# Пользователь (кастомный)
# ---------------------------
class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # AbstractUser уже содержит username, email, password, first_name, last_name
    locale = models.CharField(max_length=10, blank=True, null=True)
    settings = models.JSONField(blank=True, null=True)
    last_active_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    # Аватарка пользователя (ссылка на одно из приобретённых достижений)
    avatar_achievement = models.ForeignKey(
        "Achievement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users_with_avatar"
    )

    def mark_active(self):
        self.last_active_at = timezone.now()
        self.save(update_fields=["last_active_at"])

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
        ]


# ---------------------------
# Цели
# ---------------------------
class Goal(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("archived", "Archived"),
    ]

    VISIBILITY_CHOICES = [
        ("private", "Private"),
        ("shared", "Shared"),
        ("public", "Public"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals")
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    priority = models.SmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="private")
    meta = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "goals"
        indexes = [
            models.Index(fields=["owner"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return self.title


# ---------------------------
# AI-запросы (логирование генераций)
# ---------------------------
class AIRequest(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ai_requests")
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_requests")
    prompt = models.TextField(blank=True)
    model = models.CharField(max_length=200, blank=True)
    params = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    result = models.JSONField(blank=True, null=True)  # raw output / parsed roadmap
    error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ai_requests"
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]


# ---------------------------
# Roadmap
# ---------------------------
class Roadmap(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="roadmap")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roadmap")
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    ai_request = models.ForeignKey(AIRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="generated_roadmap")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    is_template = models.BooleanField(default=False)
    original_roadmap = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="copies")
    snapshot = models.JSONField(blank=True, null=True)  # полное дерево для быстрого восстановления
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roadmap"
        indexes = [
            models.Index(fields=["goal"]),
            models.Index(fields=["owner"]),
        ]

    def make_copy_for(self, new_owner = settings.AUTH_USER_MODEL) -> "Roadmap":
        """
        Создать копию roadmap для другого пользователя.
        Копия сохраняет snapshot и original_roadmap ссылку.
        """
        copy = Roadmap.objects.create(
            goal=self.goal,
            owner=new_owner,
            title=self.title,
            description=self.description,
            generated_by_ai=self.generated_by_ai,
            ai_request=self.ai_request,
            version=1,
            status="draft",
            is_template=False,
            original_roadmap=self,
            snapshot=self.snapshot,
        )
        # Вариант: клонировать шаги/таски отдельно (см. RoadmapStep.clone_tree)
        return copy

    def __str__(self):
        return self.title


# ---------------------------
# Расшаривание roadmap
# ---------------------------
class RoadmapShare(models.Model):
    ROLE_CHOICES = [
        ("viewer", "Viewer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="shares")
    shared_with = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_roadmap_shares")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="viewer")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "roadmap_shares"
        unique_together = ("roadmap", "shared_with")
        indexes = [
            models.Index(fields=["shared_with"]),
        ]


# ---------------------------
# Шаги roadmap (иерархия)
# ---------------------------
class RoadmapStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="steps")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    title = models.CharField(max_length=400)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    duration_days = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=30, default="todo")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_steps")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "roadmap_steps"
        indexes = [
            models.Index(fields=["roadmap", "parent"]),
        ]

    def __str__(self):
        return self.title


# ---------------------------
# Задачи (main / side)
# ---------------------------
class Task(models.Model):
    TYPE_CHOICES = [
        ("main", "Main"),
        ("side", "Side"),
    ]
    STATUS_CHOICES = [
        ("todo", "To Do"),
        ("in_progress", "In Progress"),
        ("done", "Done"),
        ("blocked", "Blocked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    step = models.ForeignKey(RoadmapStep, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=400)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="main")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="todo")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tasks"
        indexes = [
            models.Index(fields=["step", "type", "status"]),
        ]

    def __str__(self):
        return self.title


# ---------------------------
# Достижения
# ---------------------------
class Achievement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    # Можно хранить локальный файл (ImageField) или URL; здесь URL удобнее для генерируемых картинок.
    image_url = models.TextField(blank=True, null=True)
    generated_by_ai = models.BooleanField(default=False)
    ai_request = models.ForeignKey(AIRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="generated_achievements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "achievements"
        indexes = [
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title


# ---------------------------
# Сопоставление задач -> достижений (побочные задачи дают достижения)
# ---------------------------
class TaskAchievement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="task_achievements")
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="task_achievements")

    class Meta:
        db_table = "task_achievements"
        unique_together = ("task", "achievement")


# ---------------------------
# Полученные пользователем достижения
# ---------------------------
class UserAchievement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="user_achievements")
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name="users_achievements")
    earned_at = models.DateTimeField(auto_now_add=True)
    meta = models.JSONField(null=True, blank=True)  # дополнительные данные (например, why/where)

    class Meta:
        db_table = "user_achievements"
        unique_together = ("user", "achievement")
        indexes = [
            models.Index(fields=["user"]),
        ]