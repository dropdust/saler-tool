"""全部 ORM 模型（导入即注册到 Base.metadata）。"""

from saler.db.models.channels_campaigns import (
    Campaign,
    CampaignChannel,
    CampaignRound,
    Channel,
    SendRecord,
)
from saler.db.models.content import ContentTheme, ContentVariant, ContentVersion
from saler.db.models.graph import GraphEdge, GraphNode, NodeTerm
from saler.db.models.leads import Company, Contact, CrawlJob, Domain, ExclusionRule, Suppression
from saler.db.models.seeds import DomainSeedHit, Seed, ValidationRecord
from saler.db.models.system import (
    AppSetting,
    BackupRecord,
    Job,
    LlmProvider,
    OperationLog,
    SearchProvider,
)

__all__ = [
    "AppSetting",
    "BackupRecord",
    "Campaign",
    "CampaignChannel",
    "CampaignRound",
    "Channel",
    "Company",
    "Contact",
    "ContentTheme",
    "ContentVariant",
    "ContentVersion",
    "CrawlJob",
    "Domain",
    "DomainSeedHit",
    "ExclusionRule",
    "GraphEdge",
    "GraphNode",
    "Job",
    "LlmProvider",
    "NodeTerm",
    "OperationLog",
    "SearchProvider",
    "Seed",
    "SendRecord",
    "Suppression",
    "ValidationRecord",
]
