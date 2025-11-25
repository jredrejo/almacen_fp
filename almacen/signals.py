from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Persona

User = get_user_model()


@receiver(post_save, sender=User)
def create_persona_for_user(sender, instance, created, **kwargs):
    """
    Crea automáticamente una instancia de Persona al crear un nuevo usuario.
    Lo hace tanto al crearlo en el admin o usando social auth (Google) signup.
    """
    if created:
        Persona.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_persona_for_user(sender, instance, **kwargs):
    if hasattr(instance, "persona"):
        instance.persona.save()
