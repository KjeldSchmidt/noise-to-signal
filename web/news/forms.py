from django import forms

from news.models import Feed, FollowUpAnswer, LocationOfInterest


class CustomFeedForm(forms.Form):
    title = forms.CharField(max_length=200, label="Feed name")
    url = forms.URLField(label="RSS URL")
    site_url = forms.URLField(required=False, label="Site URL (optional)")
    category = forms.CharField(max_length=80, required=False, initial="Custom")
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        if Feed.objects.filter(url=url).exists():
            raise forms.ValidationError("That feed URL is already in the catalog.")
        return url


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
