from typing import List, Dict, Any, Set, Optional
import logging
import re
from pydantic import ValidationError
from app.repos.config_repo import config_repo
from app.schemas.clash_config import ClashConfig, ProxyGroup, RuleProvider

logger = logging.getLogger(__name__)

class ClashConfigService:
    def add_config_to_proxies(self, proxies: List[Dict[str, Any]], override_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Loads configuration from repo and generates the full Clash config.
        Parameters:
            proxies (List[Dict[str, Any]]): List of proxy configurations.
            override_data (Optional[Dict[str, Any]]): Additional config to merge/override.
        Returns:
            Dict[str, Any]: The complete Clash configuration dictionary.
        """
        pg_data = config_repo.load_proxy_groups()
        rules = config_repo.load_rules()
        
        return self.generate_config(proxies, pg_data, rules, override_data)
    
    def generate_config(self, 
                        proxies: List[Dict[str, Any]], 
                        proxy_groups_data: Dict[str, Any], 
                        rules_data: Dict[str, Any],
                        override_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generates the Clash config structure by processing groups and rules.
        Parameters:
            proxies (List[Dict[str, Any]]): List of proxy configurations.
            proxy_groups_data (Dict[str, Any]): Raw proxy groups configuration.
            rules_data (Dict[str, Any]): Raw rules configuration.
            override_data (Optional[Dict[str, Any]]): Additional config to merge/override.
        Returns:
            Dict[str, Any]: The complete Clash configuration dictionary.
        """
        raw_groups = proxy_groups_data.get("proxy-groups", [])

        # Extract proxy names (ordered list for unclassified handling)
        ordered_proxy_names = [p.get("name", "") for p in proxies if "name" in p]
        proxy_names_set = set(ordered_proxy_names)
        
        # 1. Process Groups
        processed_groups = self._process_groups(raw_groups, ordered_proxy_names, proxy_names_set)
        
        # 2. Process Rules
        group_names = set(g.get("name") for g in processed_groups if "name" in g)
        built_ins = {"DIRECT", "REJECT", "NO-HYDRA"}
        valid_targets = proxy_names_set.union(group_names).union(built_ins)
        processed_rules = self._process_rules(rules_data, valid_targets)

        config = ClashConfig(
            mixed_port=7890,
            allow_lan=False,
            mode="Rule",
            log_level="info",
            external_controller=":9090",
            proxies=proxies,
            proxy_groups=processed_groups,
            rules=processed_rules
        )

        final_config = config.model_dump(by_alias=True, exclude_none=True)

        if override_data:
            logger.info(f"Applying override configuration (keys: {list(override_data.keys())})")
            final_config.update(override_data)

        return final_config

    def _process_groups(self, 
                        raw_groups: List[Dict[str, Any]], 
                        ordered_proxy_names: List[str], 
                        proxy_names_set: Set[str]) -> List[Dict[str, Any]]:
        active_groups = {}
        used_proxies = set()
        
        for raw_group in raw_groups:
            try:
                # Validate against ProxyGroup schema
                group_model = ProxyGroup(**raw_group)
                group = group_model.model_dump(by_alias=True)
                # Restore removable field for internal logic as it is excluded in dump
                group['removable'] = group_model.removable
            except ValidationError as e:
                logger.warning(f"Invalid proxy group configuration: {e}")
                continue

            group_name = group.get("name")
            
            # 1. Expand Regex
            filter_regex = group.pop("filter", None)
            if filter_regex:
                try:
                    pattern = re.compile(filter_regex, re.IGNORECASE)
                    # Use ordered list to maintain order in regex matches too
                    matched = [name for name in ordered_proxy_names if pattern.search(name)]
                    group["proxies"].extend(matched)
                    used_proxies.update(matched)
                except re.error as e:
                    logger.warning(f"Invalid regex '{filter_regex}' in group '{group_name}': {e}")

            # Track explicit proxies
            for p in group["proxies"]:
                if p in proxy_names_set:
                    used_proxies.add(p)

            # Deduplicate proxies
            group["proxies"] = list(dict.fromkeys(group["proxies"]))
            
            active_groups[group_name] = group

        # 2. Handle Unclassified Proxies (Maintain Order)
        unclassified = [p for p in ordered_proxy_names if p not in used_proxies]
        
        if unclassified:
            if "PROXY" in active_groups:
                logger.info(f"Adding {len(unclassified)} unclassified proxies to PROXY group.")
                active_groups["PROXY"]["proxies"].extend(unclassified)
                active_groups["PROXY"]["proxies"] = list(dict.fromkeys(active_groups["PROXY"]["proxies"]))
            else:
                logger.warning(f"Found {len(unclassified)} unclassified proxies but 'PROXY' group does not exist.")

        built_ins = {"DIRECT", "REJECT", "NO-HYDRA"}
        base_valid_targets = proxy_names_set.union(built_ins)
        
        # 3. Iterative Pruning
        self._prune_groups(active_groups, base_valid_targets)
            
        return list(active_groups.values())

    def _prune_groups(self, active_groups: Dict[str, Dict[str, Any]], base_valid_targets: Set[str]) -> None:
        while True:
            removed_count = 0
            valid_targets = base_valid_targets.union(active_groups.keys())
            
            groups_to_remove = []
            
            for name, group in active_groups.items():
                removable = group.get("removable", False)
                
                current_proxies = group["proxies"]
                valid_proxies = []
                should_remove_group = False
                
                for p in current_proxies:
                    if p in valid_targets:
                        valid_proxies.append(p)
                    else:
                        if removable:
                            logger.warning(f"Group '{name}' (removable=True) references missing target '{p}'. Removing group.")
                            should_remove_group = True
                            break
                
                if should_remove_group:
                    groups_to_remove.append(name)
                    continue
                
                group["proxies"] = valid_proxies
                
                if not group["proxies"]:
                    logger.warning(f"Group '{name}' is empty. Removing group.")
                    groups_to_remove.append(name)
            
            for name in groups_to_remove:
                if name in active_groups:
                    del active_groups[name]
                    removed_count += 1
            
            if removed_count == 0:
                break

    def _process_rules(self, rules_data: Dict[str, Any], valid_targets: Set[str]) -> List[str]:
        if not rules_data:
            return []

        rule_providers_data = rules_data.get("rule-providers", {})
        raw_rules = rules_data.get("rules", [])
        valid_rules = []
        
        # Validate Rule Providers
        validated_providers = {}
        for name, data in rule_providers_data.items():
            try:
                provider = RuleProvider(**data)
                validated_providers[name] = provider
            except ValidationError as e:
                logger.warning(f"Invalid RuleProvider '{name}': {e}")
                continue

        for rule in raw_rules:
            if not isinstance(rule, str) or not rule.strip():
                continue
                
            parts = [p.strip() for p in rule.split(',')]
            rule_type = parts[0]
            
            if rule_type == "RULE-SET":
                if len(parts) < 3:
                    logger.warning(f"Invalid RULE-SET format: {rule}")
                    continue
                    
                provider_name = parts[1]
                target = parts[2]
                
                if target not in valid_targets:
                    logger.warning(f"RULE-SET target '{target}' invalid. Skipping.")
                    continue

                provider = validated_providers.get(provider_name)
                if not provider:
                    logger.warning(f"Provider '{provider_name}' not found or invalid.")
                    continue
                
                expanded_rules = self._expand_rule_set(provider, target)
                valid_rules.extend(expanded_rules)
                    
            else:
                target = None
                if parts[0] == "MATCH":
                    if len(parts) >= 2:
                        target = parts[1]
                elif len(parts) >= 3:
                        target = parts[2]
                
                if target:
                    if target in valid_targets:
                        valid_rules.append(rule)
                    else:
                        logger.warning(f"Rule target '{target}' invalid or missing. Skipping rule: {rule}")
                else:
                    valid_rules.append(rule)
                    
        return valid_rules

    def _expand_rule_set(self, provider: RuleProvider, target: str) -> List[str]:
        file_path = provider.path
        if not file_path:
            return []
            
        lines = config_repo.load_provider_file(file_path)
        expanded_rules = []
        for line in lines:
            line_parts = [p.strip() for p in line.split(',')]
            
            suffix = ""
            if line_parts[-1].lower() == "no-resolve":
                line_parts.pop()
                suffix = ",no-resolve"
            
            expanded_rule = f"{','.join(line_parts)},{target}{suffix}"
            expanded_rules.append(expanded_rule)
        return expanded_rules