from django import forms

from apps.telegram_bot import models as tg_models


class ShipmentCreateForm(forms.ModelForm):
    client_code = forms.CharField(label="Код клиента", max_length=32)

    def __init__(self, *args, staff_filial=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._staff_filial = staff_filial

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
        qs = tg_models.User.objects.filter(client_code=value)
        if self._staff_filial is not None:
            qs = qs.filter(filial=self._staff_filial)
        user_obj = qs.first()
        if not user_obj:
            raise forms.ValidationError("Клиент с таким кодом не найден")
        self._user_obj = user_obj
        return value

    def save(self, commit=True, staff_filial=None):
        instance = super().save(commit=False)
        instance.user = getattr(self, "_user_obj", None)
        instance.filial = staff_filial if staff_filial is not None else getattr(instance.user, "filial", None)
        if commit:
            instance.save()
        return instance


class ShipmentImportForm(forms.Form):
    file = forms.FileField(label="Excel файл (.xlsx)")
    sent_date = forms.DateField(label="Дата отправки", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    group_status = forms.ChoiceField(
        label="Статус группы",
        choices=tg_models.ShipmentGroup.Status.choices,
        initial=tg_models.ShipmentGroup.Status.ON_THE_WAY,
    )
    price_per_kg = forms.DecimalField(label="Цена за кг", required=False, decimal_places=2, max_digits=12)


class ClientEditManagerForm(forms.Form):
    client_code = forms.CharField(label="Код клиента", required=False, max_length=32)
    full_name = forms.CharField(label="ФИО", required=False, max_length=255)
    phone = forms.CharField(label="Телефон", required=False, max_length=64)
    address = forms.CharField(label="Адрес", required=False, max_length=512)


class ClientEditDirectorForm(forms.ModelForm):
    class Meta:
        model = tg_models.User
        fields = [
            "client_code",
            "telegram_id",
            "username",
            "first_name",
            "last_name",
            "language_code",
            "full_name",
            "phone",
            "address",
            "filial",
            "client_type",
            "client_status",
            "status",
            "total_debt",
        ]


ClientEditForm = ClientEditManagerForm
