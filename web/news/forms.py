from typing import Any, cast

from django import forms
from django.utils.translation import gettext_lazy as _

from news.models import Feed, LocationOfInterest
from news.services.feeds import catalog_languages, content_language_labels


class CustomFeedForm(forms.Form):
    title = forms.CharField(max_length=200, label=_("Feed name"), required=False)
    url = forms.URLField(label=_("RSS URL"))
    site_url = forms.URLField(required=False, label=_("Site URL (optional)"))
    category = forms.CharField(max_length=80, required=False, initial="Custom")
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_url(self) -> str:
        return str(self.cleaned_data["url"]).strip()

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        url = str(cleaned.get("url") or "").strip()
        title = str(cleaned.get("title") or "").strip()
        if url and not Feed.objects.filter(url=url).exists() and not title:
            self.add_error("title", _("A name is required for new feeds."))
        cleaned["title"] = title
        return cleaned


class ContentLanguagesForm(forms.Form):
    """Accepted content languages plus one primary for UI and story copy."""

    languages = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[],
        label=_("Languages to include"),
    )
    primary = forms.ChoiceField(
        required=False,
        widget=forms.RadioSelect,
        choices=[],
        label=_("Primary language"),
        help_text=_("Used for the interface and for story titles and summaries when available."),
    )

    def __init__(self, *args: Any, available: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        codes = available if available is not None else catalog_languages()
        if not codes:
            codes = ["en"]
        labels = content_language_labels()
        choices = [(code, labels.get(code, code.upper())) for code in codes]
        languages_field = cast(forms.MultipleChoiceField, self.fields["languages"])
        primary_field = cast(forms.ChoiceField, self.fields["primary"])
        languages_field.choices = choices
        primary_field.choices = choices

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        selected = [str(code).strip().lower() for code in (cleaned.get("languages") or []) if code]
        if not selected:
            selected = ["en"]
        primary = str(cleaned.get("primary") or "").strip().lower()
        if primary not in selected:
            primary = "en" if "en" in selected else selected[0]
        cleaned["languages"] = selected
        cleaned["primary"] = primary
        return cleaned


class LocationOfInterestForm(forms.ModelForm):
    class Meta:
        model = LocationOfInterest
        fields = (
            "label",
            "latitude",
            "longitude",
            "country_code",
            "admin1",
            "locality",
            "geo_level",
        )
        widgets = {
            "label": forms.HiddenInput(attrs={"id": "id_location_label"}),
            "latitude": forms.HiddenInput(attrs={"id": "id_location_lat"}),
            "longitude": forms.HiddenInput(attrs={"id": "id_location_lng"}),
            "country_code": forms.HiddenInput(attrs={"id": "id_location_country"}),
            "admin1": forms.HiddenInput(attrs={"id": "id_location_admin1"}),
            "locality": forms.HiddenInput(attrs={"id": "id_location_locality"}),
            "geo_level": forms.HiddenInput(attrs={"id": "id_location_geo_level"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["latitude"].required = False
        self.fields["longitude"].required = False
        self.fields["label"].required = True
        for name in ("country_code", "admin1", "locality", "geo_level"):
            self.fields[name].required = False
