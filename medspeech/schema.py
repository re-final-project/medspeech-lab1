from pydantic import BaseModel, ConfigDict, Field, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class Measurement(Evidence):
    unit: str | None


class Consultation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    purpose: Evidence | None = None
    symptoms: list[Evidence] = Field(default_factory=list)
    denied_symptoms: list[Evidence] = Field(default_factory=list)
    medications: list[Evidence] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_conflict(self):
        if {x.value for x in self.symptoms} & {x.value for x in self.denied_symptoms}:
            raise ValueError("same symptom cannot be both present and denied")
        return self


def items(result):
    for field in Consultation.model_fields:
        values = getattr(result, field)
        for value in ([values] if field == "purpose" and values else values or []):
            yield field, value


def grounded(result, text):
    return all(x.evidence in text and x.value in x.evidence and
               (not isinstance(x, Measurement) or x.unit is None or x.unit in x.evidence)
               for _, x in items(result))


def invalid_json_object_prefix(text):
    prefix=text.lstrip()
    return bool(prefix and not prefix.startswith("{"))
