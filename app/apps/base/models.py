from django.db import models
# Create your models here.

class Settings(models.Model):
    title = models.CharField(max_length=255, verbose_name="Название карго")
    manager_contact = models.CharField(max_length=255, verbose_name="Контакт менеджера")
    logo = models.ImageField(upload_to="logo", verbose_name="Логотип")