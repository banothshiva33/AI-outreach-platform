from abc import ABC, abstractmethod
import logging
from typing import List, Type

from app.discovery.types import ExtractedCompany, SearchResult

logger = logging.getLogger(__name__)


class BaseSearchPlugin(ABC):
    name: str = "base"
    priority: int = 100

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def search(self, keyword: str, *, limit: int = 10) -> List[SearchResult]:
        pass


class BaseDirectoryConnector(ABC):
    """Scrapes startup directory sites for company listings."""

    name: str = "base"
    priority: int = 50

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def discover(self, keyword: str, *, limit: int = 10) -> List[ExtractedCompany]:
        pass


class PluginRegistry:
    def __init__(self):
        self._search_plugins: List[BaseSearchPlugin] = []
        self._directory_connectors: List[BaseDirectoryConnector] = []

    def register_search(self, plugin: BaseSearchPlugin) -> None:
        if not any(p.name == plugin.name for p in self._search_plugins):
            self._search_plugins.append(plugin)
            self._search_plugins.sort(key=lambda p: p.priority)

    def register_directory(self, connector: BaseDirectoryConnector) -> None:
        if not any(c.name == connector.name for c in self._directory_connectors):
            self._directory_connectors.append(connector)
            self._directory_connectors.sort(key=lambda c: c.priority)

    def get_search_plugins(self) -> List[BaseSearchPlugin]:
        return [p for p in self._search_plugins if p.is_available()]

    def get_directory_connectors(self) -> List[BaseDirectoryConnector]:
        return [c for c in self._directory_connectors if c.is_available()]

    def search(self, keyword: str, *, limit: int = 10) -> List[SearchResult]:
        plugins = self.get_search_plugins()
        if not plugins:
            logger.error("No search plugins available")
            return []

        results: List[SearchResult] = []
        seen_urls = set()
        for plugin in plugins:
            try:
                for item in plugin.search(keyword, limit=limit):
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        results.append(item)
                    if len(results) >= limit:
                        return results
            except Exception as exc:
                logger.warning(
                    "Search plugin '%s' failed for '%s': %s", plugin.name, keyword, exc
                )
        return results

    def discover_directories(
        self, keyword: str, *, limit: int = 10
    ) -> List[ExtractedCompany]:
        companies: List[ExtractedCompany] = []
        seen = set()
        per_connector = max(3, limit // max(len(self.get_directory_connectors()), 1))

        for connector in self.get_directory_connectors():
            try:
                for company in connector.discover(keyword, limit=per_connector):
                    key = company.name.strip().lower()
                    if key not in seen:
                        seen.add(key)
                        companies.append(company)
                    if len(companies) >= limit:
                        return companies
            except Exception as exc:
                logger.warning(
                    "Directory connector '%s' failed for '%s': %s",
                    connector.name,
                    keyword,
                    exc,
                )
        return companies


plugin_registry = PluginRegistry()


def register_search_plugin(plugin_cls: Type[BaseSearchPlugin]) -> Type[BaseSearchPlugin]:
    plugin_registry.register_search(plugin_cls())
    return plugin_cls


def register_directory_connector(
    connector_cls: Type[BaseDirectoryConnector],
) -> Type[BaseDirectoryConnector]:
    plugin_registry.register_directory(connector_cls())
    return connector_cls
