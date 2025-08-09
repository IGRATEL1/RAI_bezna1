from rest_framework import serializers
from .models import AIRequest, Roadmap, RoadmapStep, Task, Achievement, UserAchievement

class AIRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIRequest
        fields = "__all__"
        read_only_fields = ("id","user","status","result","error","created_at","completed_at")


class RoadmapSerializer(serializers.ModelSerializer):
    class Meta:
        model = Roadmap
        fields = ("id","owner","title","description","snapshot","created_at","original_roadmap")
        read_only_fields = ("id","owner","created_at")


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = "__all__"
        read_only_fields = ("id","created_at")


class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = "__all__"
        read_only_fields = ("id","created_at")
