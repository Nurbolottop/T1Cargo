from django import forms

from apps.telegram_bot import models as tg_models


class ShipmentCreateForm(forms.ModelForm):
    client_code = forms.CharField(label="Код клиента (только номер)", max_length=32, help_text="Например: 1957 (вводите только номер, без префикса)")
    pricing_mode = forms.ChoiceField(
        label="Способ расчёта",
        choices=[("", "—"), ("kg", "По кг"), ("gabarit", "По габариту")],
        required=False,
    )
    length_cm = forms.DecimalField(label="Длина (см)", required=False, min_value=0, decimal_places=2, max_digits=10)
    width_cm = forms.DecimalField(label="Ширина (см)", required=False, min_value=0, decimal_places=2, max_digits=10)
    height_cm = forms.DecimalField(label="Высота (см)", required=False, min_value=0, decimal_places=2, max_digits=10)

    def __init__(self, *args, staff_filial=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._staff_filial = staff_filial
        groups_qs = tg_models.ShipmentGroup.objects.all().order_by("-created_at")
        if self._staff_filial is not None:
            groups_qs = groups_qs.filter(filial=self._staff_filial)
        self.fields["group"].queryset = groups_qs
        # Remove status from visible fields - will be auto-set from group
        if "status" in self.fields:
            del self.fields["status"]
        # Remove tracking_number from visible fields - will be handled in view
        if "tracking_number" in self.fields:
            del self.fields["tracking_number"]

    class Meta:
        model = tg_models.Shipment
        fields = [
            "client_code",
            "group",
            "weight_kg",
            "price_per_kg",
            "total_price",
            "arrival_date",
            "pricing_mode",
            "length_cm",
            "width_cm",
            "height_cm",
        ]
        widgets = {
            "arrival_date": forms.DateInput(attrs={"type": "date"}),
            "price_per_kg": forms.NumberInput(attrs={"step": "0.01", "placeholder": "Авто из филиала"}),
        }

    def clean_group(self):
        group = self.cleaned_data.get("group")
        if group is None:
            return None
        if self._staff_filial is not None and group.filial_id != self._staff_filial.id:
            raise forms.ValidationError("Группа должна быть из выбранного филиала")
        return group

    def clean_client_code(self):
        value = (self.cleaned_data.get("client_code") or "").strip()
        if not value:
            raise forms.ValidationError("Укажите код клиента")
        
        # Try exact match first
        qs = tg_models.User.objects.filter(client_code=value)
        if self._staff_filial is not None:
            qs = qs.filter(filial=self._staff_filial)
        user_obj = qs.first()
        
        # If not found, try matching by suffix (number part after hyphen)
        if not user_obj:
            qs = tg_models.User.objects.filter(client_code__endswith=f"-{value}")
            if self._staff_filial is not None:
                qs = qs.filter(filial=self._staff_filial)
            user_obj = qs.first()
        
        if not user_obj:
            raise forms.ValidationError("Клиент с таким кодом не найден. Введите полный код (например, T1-1234) или только номер (например, 1234).")
        self._user_obj = user_obj
        return value

    def save(self, commit=True, staff_filial=None, tracking_number=None, weight_kg=None, price_per_kg=None, total_price=None):
        instance = super().save(commit=False)
        instance.user = getattr(self, "_user_obj", None)
        instance.filial = staff_filial if staff_filial is not None else getattr(instance.user, "filial", None)
        instance.group = self.cleaned_data.get("group")
        if tracking_number:
            instance.tracking_number = tracking_number
        # Apply passed values AFTER super().save() to override form values
        if weight_kg is not None:
            instance.weight_kg = weight_kg
        if total_price is not None:
            instance.total_price = total_price
        # If price_per_kg not provided, use filial's default_price_per_kg
        if price_per_kg is not None:
            instance.price_per_kg = price_per_kg
        elif instance.filial and getattr(instance.filial, "default_price_per_kg", None):
            instance.price_per_kg = instance.filial.default_price_per_kg
        instance.status = tg_models.Shipment.Status.WAREHOUSE
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
