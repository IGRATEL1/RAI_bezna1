from django.urls import path
from . import views

urlpatterns = [
    path("goals/<uuid:goal_id>/generate/", views.generate_roadmap, name="generate-roadmap"),
    path("ai-requests/<uuid:ai_request_id>/", views.ai_request_status, name="ai-request-status"),
    path("roadmap/<uuid:roadmap_id>/copy/", views.copy_roadmap, name="copy-roadmap"),
    path("tasks/<uuid:task_id>/complete/", views.complete_task, name="complete-task"),
    path("users/<uuid:user_id>/avatar/", views.set_avatar, name="set-avatar"),
]