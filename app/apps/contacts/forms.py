from django import forms

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
    group_status = forms.ChoiceField(label="Статус группы", choices=tg_models.ShipmentGroup.Status.choices)
    shipment_status = forms.ChoiceField(
        label="Статус товаров",
        choices=[
            (tg_models.Shipment.Status.ON_THE_WAY, "В пути"),
            (tg_models.Shipment.Status.WAREHOUSE, "На складе"),
        ],
    )
    price_per_kg = forms.DecimalField(label="Цена за кг", required=False, decimal_places=2, max_digits=12)
