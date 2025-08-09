from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.conf import settings
from .models import AIRequest, Roadmap, RoadmapStep, Task, Achievement, UserAchievement
from .serializers import AIRequestSerializer, RoadmapSerializer, TaskSerializer, AchievementSerializer
from .generator_client import call_generator
from .utils import save_image_from_base64, fetch_and_save_image
from django.db import transaction
from time import timezone

# ========== Generate endpoint ==========
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def generate_roadmap(request, goal_id):
    """
    POST /api/v1/goals/{goal_id}/generate/
    Body: { prompt_overrides: str, constraints: {...} }
    """
    user = request.user
    prompt = request.data.get("prompt_overrides", "")
    params = request.data.get("constraints", {})

    # idempotency check
    idempotency_key = request.headers.get("Idempotency-Key") or request.data.get("idempotency_key")
    if idempotency_key:
        existing = AIRequest.objects.filter(user=user, idempotency_key=idempotency_key).first()
        if existing:
            # return existing request
            serializer = AIRequestSerializer(existing)
            return Response(serializer.data, status=200)

    ai = AIRequest.objects.create(user=user, goal_id=goal_id, prompt=prompt, params=params, idempotency_key=idempotency_key, status="running")

    # Call generator synchronously (MVP)
    gen_resp = call_generator(str(ai.id), str(user.id), {"id": str(goal_id)}, prompt, params)

    # handle generator response
    if gen_resp.get("status") == "succeeded":
        # save roadmap & achievements atomically
        try:
            with transaction.atomic():
                roadmap_data = gen_resp.get("roadmap", {})
                title = roadmap_data.get("title") or f"Roadmap {ai.id}"
                snapshot = roadmap_data  # for quick restore
                roadmap = Roadmap.objects.create(owner=user, title=title, description=roadmap_data.get("description",""), snapshot=snapshot)

                # steps & tasks (optional)
                for i, step in enumerate(roadmap_data.get("steps", [])):
                    rstep = RoadmapStep.objects.create(roadmap=roadmap, title=step.get("title","Step"), order=step.get("order", i))
                    for t in step.get("tasks", []):
                        Task.objects.create(step=rstep, title=t.get("title","Task"), type=t.get("type","main"))

                # achievements
                created_achievements = []
                for ach in gen_resp.get("achievements", []):
                    # ach may contain image_base64 or image_url
                    image_relpath = None
                    if ach.get("image_base64"):
                        image_relpath = save_image_from_base64(ach["image_base64"])
                    elif ach.get("image_url"):
                        image_relpath = fetch_and_save_image(ach["image_url"])

                    achievement = Achievement.objects.create(
                        title=ach.get("title","Achievement"),
                        description=ach.get("description",""),
                        image=image_relpath and f"{settings.MEDIA_URL}{image_relpath}" or None,
                        image_url=ach.get("image_url") if ach.get("image_url") else None,
                        generated_by_ai=True
                    )
                    created_achievements.append(AchievementSerializer(achievement).data)

                # update ai request
                ai.status = "succeeded"
                ai.result = gen_resp
                ai.completed_at = timezone.now()
                ai.save()

                ser = RoadmapSerializer(roadmap)
                return Response({"ai_request_id": str(ai.id), "roadmap": ser.data, "achievements": created_achievements}, status=201)
        except Exception as e:
            ai.status = "failed"
            ai.error = str(e)
            ai.save()
            return Response({"detail": "Failed to save generated roadmap", "error": str(e)}, status=500)

    elif gen_resp.get("status") == "queued":
        # generator accepted and will process async; save whatever info
        ai.status = "queued"
        ai.result = gen_resp
        ai.save()
        return Response({"ai_request_id": str(ai.id), "status": "queued"}, status=202)
    else:
        ai.status = "failed"
        ai.error = gen_resp.get("error") or "generator error"
        ai.save()
        return Response({"detail": "generator failed", "error": ai.error}, status=502)


# ========== AIRequest status ==========
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def ai_request_status(request, ai_request_id):
    ai = get_object_or_404(AIRequest, id=ai_request_id, user=request.user)
    serializer = AIRequestSerializer(ai)
    return Response(serializer.data)


# ========== Copy roadmap ==========
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def copy_roadmap(request, roadmap_id):
    roadmap = get_object_or_404(Roadmap, id=roadmap_id)
    new_title = request.data.get("new_title", f"Copy of {roadmap.title}")
    new = Roadmap.objects.create(owner=request.user, title=new_title, description=roadmap.description, snapshot=roadmap.snapshot, original_roadmap=roadmap)
    # shallow copy steps/tasks if needed (MVP: skip deep clone or clone minimal)
    for step in roadmap.steps.all():
        new_step = RoadmapStep.objects.create(roadmap=new, title=step.title, order=step.order)
        for t in step.tasks.all():
            Task.objects.create(step=new_step, title=t.title, type=t.type)
    ser = RoadmapSerializer(new)
    return Response(ser.data, status=201)


# ========== Complete task (and award achievement if side task) ==========
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    # security: only assignee or owner of roadmap can mark done (MVP: allow owner)
    if task.step.roadmap.owner != request.user:
        return Response({"detail": "Not allowed"}, status=403)
    task.status = "done"
    task.save()
    granted = []
    if task.type == "side":
        # MVP logic: create a simple achievement for this task (or map to existing)
        ach_title = f"Completed side task: {task.title}"
        ach = Achievement.objects.create(title=ach_title, description=f"Автоматически создано за выполнение '{task.title}'", generated_by_ai=False)
        UserAchievement.objects.create(user=request.user, achievement=ach)
        granted.append(AchievementSerializer(ach).data)
    return Response({"task": TaskSerializer(task).data, "granted_achievements": granted})


# ========== Set avatar from achievement ==========
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def set_avatar(request, user_id):
    if str(request.user.id) != str(user_id):
        return Response({"detail": "Not allowed"}, status=403)
    achievement_id = request.data.get("achievement_id")
    if not achievement_id:
        return Response({"detail": "achievement_id required"}, status=400)
    ach = get_object_or_404(Achievement, id=achievement_id)
    # check user owns it
    if not UserAchievement.objects.filter(user=request.user, achievement=ach).exists():
        return Response({"detail": "User does not own this achievement"}, status=403)
    # set avatar_achievement (we assume User model has avatar_achievement FK)
    user = request.user
    user.avatar_achievement_id = ach.id
    user.save(update_fields=["avatar_achievement_id"])
    return Response({"detail": "avatar set"}, status=200)
