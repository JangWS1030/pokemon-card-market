from django.urls import path

from . import views


urlpatterns = [
    path('health/', views.health, name='health'),
    path('', views.home, name='home'),
    path('cards/', views.card_list, name='card-list'),
    path('cards/<int:pk>/', views.card_detail, name='card-detail'),
]
