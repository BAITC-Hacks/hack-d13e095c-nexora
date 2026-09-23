from pydantic import BaseModel, ConfigDict, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)


class PatchSchema(Schema):
    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self
