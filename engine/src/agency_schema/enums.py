"""Closed vocabularies. Carrier is deliberately not here: it is an open string."""

from enum import StrEnum


class LineOfBusiness(StrEnum):
    MA = "MA"
    PDP = "PDP"
    MEDSUPP = "MEDSUPP"
    ACA = "ACA"


class PolicyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    TERMINATED = "TERMINATED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class AgentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


class CommissionType(StrEnum):
    NEW = "NEW"
    RENEWAL = "RENEWAL"
    OVERRIDE = "OVERRIDE"
    CHARGEBACK = "CHARGEBACK"


class EligibilityReason(StrEnum):
    AGE = "AGE"
    DISABILITY = "DISABILITY"
    ESRD = "ESRD"


class Severity(StrEnum):
    BLOCKER = "BLOCKER"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class Family(StrEnum):
    """Rule families. A rule id is its family plus a number, for example DOB-001."""

    ING = "ING"
    MAP = "MAP"
    SSN = "SSN"
    CMP = "CMP"
    DOB = "DOB"
    MBI = "MBI"
    NPN = "NPN"
    PLN = "PLN"
    ADR = "ADR"
    CON = "CON"
    DAT = "DAT"
    STA = "STA"
    DUP = "DUP"
    REF = "REF"
    RTS = "RTS"
    LIC = "LIC"
    TIE = "TIE"
    PII = "PII"


class Lane(StrEnum):
    """Where an exception goes in the review queue. Set by triage in PR 11."""

    SUGGESTED_FIX = "SUGGESTED_FIX"
    REVIEW = "REVIEW"
    BUSINESS_EVENT = "BUSINESS_EVENT"
    UNREVIEWED = "UNREVIEWED"


class JevMode(StrEnum):  # replay is the default; live and record spend money
    REPLAY = "replay"
    OFF = "off"
    LIVE = "live"
    RECORD = "record"
