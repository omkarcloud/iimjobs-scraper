"""Marshmallow request schemas for every /iimjobs/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the iimjobs resolvers (refs.py) and the job-board fields (experience
years, the optional resolver field) that hirist/schemas.py also defines.
Every schema's load() output is the kwargs dict its endpoint function
takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes a job id OR any iimjobs job link;
`company` a company id, a page slug, a /<slug>-careers link or a name;
`recruiter` an id or a profile link; `course` an id or a course link;
`location` the picker's names or ids (alternate spellings, "remote", the
umbrella groups); `category` ids, slugs or names; `industry` names or ids
(trending ones as names or t-<id>); `skill` tag names or ids (comma lists).
"""
from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import BaseSchema, Flag, PageField, PageSizeField, QueryField, RefField, StrippedString
from iimjobs import refdata, refs


def _max_length(n):
    """validate.Length(max=n) that tolerates the None StrippedString returns
    for an empty value (marshmallow runs validators on it; len(None) is a 500)."""
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check

class _OptionalRef(RefField):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class JobListField(RefField):
    resolver = staticmethod(refs.resolve_jobs)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class RecruiterField(RefField):
    resolver = staticmethod(refs.resolve_recruiter)


class CourseField(RefField):
    resolver = staticmethod(refs.resolve_course)


class LocationListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_locations)


class CategoryListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_categories)


class IndustryListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_industries)


class SkillListField(_OptionalRef):
    resolver = staticmethod(refs.resolve_skills)

class ExperienceYearsField(fields.Integer):
    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.Range(min=0, max=refdata.MAX_EXPERIENCE_YEARS))
        super().__init__(strict=False, **kwargs)


class PostedWithinField(fields.Integer):
    """Days (any count: 1 = today, 7 = this week, 30, 90 …)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", None)
        kwargs.setdefault("validate", validate.Range(min=1, max=refdata.MAX_POSTED_WITHIN_DAYS))
        super().__init__(strict=False, **kwargs)


def _experience_band(data):
    lo, hi = data.get("min_experience"), data.get("max_experience")
    if lo is not None and hi is not None and lo > hi:
        raise ValidationError("Must not exceed max_experience.", "min_experience")


# ---- jobs ----------------------------------------------------------------------------------------------------

class JobSearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(200))
    skill = SkillListField()
    category = CategoryListField()
    location = LocationListField()
    industry = IndustryListField()
    min_experience = ExperienceYearsField()
    max_experience = ExperienceYearsField()
    posted_within = PostedWithinField()
    smart_search = Flag(load_default=False)
    page = PageField(max_page=refdata.MAX_PAGE)
    page_size = PageSizeField(default=refdata.PAGE_SIZE, max_size=refdata.MAX_PAGE_SIZE)
    include_details = Flag(load_default=False)

    @validates_schema
    def _check(self, data, **kwargs):
        _experience_band(data)
        if (data.get("page", 1) - 1) * data.get("page_size", refdata.PAGE_SIZE) >= refdata.MAX_RESULTS_WINDOW:
            raise ValidationError(f"iimjobs serves the first {refdata.MAX_RESULTS_WINDOW:,} results of a listing; "
                                  "page * page_size is past it (narrow the filters instead).", "page")


class WomenJobsSchema(BaseSchema):
    location = LocationListField()
    category = CategoryListField()
    min_experience = ExperienceYearsField()
    max_experience = ExperienceYearsField()
    page = PageField(max_page=refdata.MAX_PAGE)
    page_size = PageSizeField(default=refdata.PAGE_SIZE, max_size=refdata.MAX_PAGE_SIZE)

    @validates_schema
    def _check(self, data, **kwargs):
        _experience_band(data)


class JobSchema(BaseSchema):
    job = JobField()


class JobBatchSchema(BaseSchema):
    jobs = JobListField()


class SimilarJobsSchema(BaseSchema):
    job = JobField()
    limit = fields.Integer(load_default=20, strict=False, validate=validate.Range(min=1, max=refdata.SIMILAR_LIMIT - 1))


# ---- companies ----------------------------------------------------------------------------------------------------

class CompanySearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    page = PageField(max_page=refdata.COMPANY_LIST_MAX_PAGE)

    @validates_schema
    def _check(self, data, **kwargs):
        if data.get("query") and data.get("page", 1) > 1:
            raise ValidationError("A name search returns one page; `page` pages the directory (no `query`).", "page")


class CompanySchema(BaseSchema):
    company = CompanyField()
    include_jobs = Flag(load_default=True)


class CompanyJobsSchema(BaseSchema):
    company = CompanyField()
    page = PageField(max_page=refdata.MAX_PAGE)


# ---- recruiters ----------------------------------------------------------------------------------------------------

class RecruiterSchema(BaseSchema):
    recruiter = RecruiterField()


class RecruiterJobsSchema(BaseSchema):
    recruiter = RecruiterField()
    page = PageField(max_page=refdata.MAX_PAGE)


# ---- courses ------------------------------------------------------------------------------------------------------

class CourseSearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    category = CategoryListField()
    delivery_method = StrippedString(required=False, load_default=None, validate=_max_length(40))
    max_work_experience = ExperienceYearsField()


class CourseSchema(BaseSchema):
    course = CourseField()


# ---- lookups ------------------------------------------------------------------------------------------------------------

class SkillsSchema(BaseSchema):
    category = CategoryListField()
    query = StrippedString(required=False, load_default=None, validate=_max_length(80))
    limit = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=1, max=1000))


class AutocompleteSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = fields.Integer(load_default=10, strict=False, validate=validate.Range(min=1, max=50))


class EmptySchema(BaseSchema):
    pass
