"""
Configuration Manager
Gère le chargement et la validation de la configuration
"""
import json
import os
from typing import Dict, Any
from pathlib import Path
from loguru import logger


class ConfigManager:
    """Gestionnaire de configuration pour le bot d'arbitrage"""
    
    def __init__(self, config_path: str = None):
        """
        Initialise le gestionnaire de configuration
        
        Args:
            config_path: Chemin vers le fichier de configuration
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._validate_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Charge la configuration depuis le fichier JSON"""
        if not self.config_path.exists():
            logger.warning(f"Config file not found at {self.config_path}")
            logger.info("Copying from config.example.json")
            
            example_path = self.config_path.parent / "config.example.json"
            if example_path.exists():
                import shutil
                shutil.copy(example_path, self.config_path)
            else:
                raise FileNotFoundError("No config file or example found")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _validate_config(self):
        """Valide la configuration chargée"""
        required_sections = ['exchanges', 'trading', 'arbitrage', 'monitoring']
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required config section: {section}")
        
        # Vérifier les clés API
        for exchange in ['extended', 'variational']:
            if exchange in self.config['exchanges']:
                api_key = self.config['exchanges'][exchange].get('api_key', '')
                if 'YOUR_' in api_key:
                    logger.warning(f"Please configure {exchange} API keys in config.json")
    
    def get(self, *keys, default=None) -> Any:
        """
        Récupère une valeur de configuration
        
        Args:
            *keys: Chemin vers la valeur (ex: 'exchanges', 'extended', 'api_key')
            default: Valeur par défaut si la clé n'existe pas
            
        Returns:
            La valeur de configuration ou default
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def get_exchange_config(self, exchange_name: str) -> Dict[str, Any]:
        """Récupère la configuration d'un exchange"""
        return self.config['exchanges'].get(exchange_name, {})
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Récupère la configuration de trading"""
        return self.config['trading']
    
    def get_arbitrage_config(self) -> Dict[str, Any]:
        """Récupère la configuration d'arbitrage"""
        return self.config['arbitrage']
    
    def get_pairs(self) -> list:
        """Récupère la liste des paires à trader"""
        return self.config.get('pairs', [])
    
    def save(self):
        """Sauvegarde la configuration"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Configuration saved to {self.config_path}")


# Instance globale
config = None

def get_config(config_path: str = None) -> ConfigManager:
    """
    Récupère l'instance globale de configuration
    
    Args:
        config_path: Chemin optionnel vers le fichier de configuration
        
    Returns:
        Instance de ConfigManager
    """
    global config
    if config is None:
        config = ConfigManager(config_path)
    return config
