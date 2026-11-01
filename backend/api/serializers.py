"""DRF Serializers for request validation (PRD Section 4.11 & 5.2)."""

from rest_framework import serializers


class LocationInputSerializer(serializers.Serializer):  # type: ignore[type-arg]
    label = serializers.CharField(required=False, allow_blank=True, max_length=250)
    lat = serializers.FloatField(required=False, min_value=-90.0, max_value=90.0)
    lng = serializers.FloatField(required=False, min_value=-180.0, max_value=180.0)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        label = str(attrs.get("label") or "").strip()
        lat = attrs.get("lat")
        lng = attrs.get("lng")
        if not label and (lat is None or lng is None):
            raise serializers.ValidationError(
                "Either a location label or valid (lat, lng) coordinates must be provided."
            )
        return attrs


class AnalysisOptionsSerializer(serializers.Serializer):  # type: ignore[type-arg]
    gustAware = serializers.BooleanField(required=False, default=False)
    demoScenario = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=50
    )


class AnalyzeRequestSerializer(serializers.Serializer):  # type: ignore[type-arg]
    origin = LocationInputSerializer()
    destination = LocationInputSerializer()
    departureTime = serializers.CharField(max_length=64)
    loadWeightLb = serializers.FloatField(min_value=0.01, max_value=500000.0)
    intervalMiles = serializers.ChoiceField(choices=[10, 25, 50], default=25)
    options = AnalysisOptionsSerializer(required=False)
