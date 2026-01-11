from django import forms
import re

from apps.telegram_bot import models as tg_models


class ShipmentCreateForm(forms.ModelForm):
    client_code = forms.CharField(label="Код клиента", max_length=32)

    class Meta:
        model = tg_models.Shipment
        fields = [
            "client_code",
            "tracking_number",
            "status",
            "weight_kg",
            "price_per_kg",
            "total_price",
            "arrival_date",
        ]

    def clean_client_code(self):
        value = (self.cleaned_data.get("client_code") or "").strip()
        if not value:
            raise forms.ValidationError("Укажите код клиента")
        user_obj = tg_models.User.objects.filter(client_code=value).first()
        if not user_obj:
            raise forms.ValidationError("Клиент с таким кодом не найден")
        self._user_obj = user_obj
        return value

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.user = getattr(self, "_user_obj", None)
        if commit:
            instance.save()
        return instance


class ShipmentImportForm(forms.Form):
    file = forms.FileField(label="Excel файл (.xlsx)")
    status = forms.ChoiceField(label="Статус", choices=tg_models.Shipment.Status.choices)
    price_per_kg = forms.DecimalField(label="Цена за кг", required=False, decimal_places=2, max_digits=12)


class PreClientCreateForm(forms.Form):
    client_code = forms.CharField(label="Код клиента", max_length=32)
    phone = forms.CharField(label="Телефон", max_length=64)

    def clean_client_code(self):
        value = (self.cleaned_data.get("client_code") or "").strip()
        if not value:
            raise forms.ValidationError("Укажите код клиента")
        if not value.isdigit():
            raise forms.ValidationError("Код клиента должен содержать только цифры")
        exists = tg_models.PreClient.objects.filter(client_code__iexact=value).exists() or tg_models.User.objects.filter(
            client_code__iexact=value
        ).exists()
        if exists:
            raise forms.ValidationError("Код уже используется")
        return value

    def clean_phone(self):
        raw = (self.cleaned_data.get("phone") or "").strip()
        if not raw:
            raise forms.ValidationError("Укажите телефон")
        digits = re.sub(r"\D+", "", raw)
        if not digits:
            raise forms.ValidationError("Укажите телефон")
        if len(digits) < 5:
            raise forms.ValidationError("Телефон слишком короткий")
        return digits

