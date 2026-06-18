from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet, TaskViewSet

router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="project")
router.register(r"tasks", TaskViewSet, basename="task")

urlpatterns = router.urls
