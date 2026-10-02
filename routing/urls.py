from django.urls import path
from .views import RoutePlannerView

urlpatterns = [
    path('api/route/', RoutePlannerView.as_view(), name='plan_route'),
]