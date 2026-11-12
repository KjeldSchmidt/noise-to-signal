from typing import Any, cast

from django import forms

from news.models import Feed, FollowUpAnswer, LocationOfInterest
from news.services.feeds import CONTENT_LANGUAGE_LABELS, catalog_languages


class CustomFeedForm(forms.Form):
    title = forms.CharField(max_length=200, label="Feed name", required=False)
    url = forms.URLField(label="RSS URL")
    site_url = forms.URLField(required=False, label="Site URL (optional)")
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
            self.add_error("title", "A name is required for new feeds.")
        cleaned["title"] = title
        return cleaned


class ContentLanguagesForm(forms.Form):
    """Multi-select of content languages the user wants to read."""

    languages = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[],
    )

    def __init__(self, *args: Any, available: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        codes = available if available is not None else catalog_languages()
        if not codes:
            codes = ["en"]
        languages_field = cast(forms.MultipleChoiceField, self.fields["languages"])
        languages_field.choices = [
            (code, CONTENT_LANGUAGE_LABELS.get(code, code.upper())) for code in codes
        ]


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


class FollowUpAnswerForm(forms.ModelForm):
    class Meta:
        model = FollowUpAnswer
        fields = ("answer",)
        widgets = {
            "answer": forms.Textarea(
                attrs={"rows": 3, "placeholder": "A sentence or two is enough…"}
            ),
        }
