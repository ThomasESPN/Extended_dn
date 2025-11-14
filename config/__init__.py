"""
Configuration Manager
Gère le chargement et la validation de la configuration
Supporte les variables d'environnement depuis un fichier .env
"""
import json
import os
from typing import Dict, Any
from pathlib import Path
from loguru import logger

# Essayer d'importer python-dotenv pour charger les variables .env
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False
    logger.warning("python-dotenv not installed. Install it with: pip install python-dotenv")


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
        self._load_env()  # Charger les variables d'environnement en premier
        self.config = self._load_config()
        self._override_with_env()  # Remplacer les valeurs par celles du .env
        self._validate_config()
    
    def _load_env(self):
        """Charge les variables d'environnement depuis un fichier .env"""
        if HAS_DOTENV:
            # Chercher le fichier .env dans le répertoire parent (racine du projet)
            env_path = self.config_path.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                logger.debug(f"Loaded environment variables from {env_path}")
            else:
                # Essayer aussi dans le répertoire config
                env_path = self.config_path.parent / ".env"
                if env_path.exists():
                    load_dotenv(env_path)
                    logger.debug(f"Loaded environment variables from {env_path}")
                else:
                    logger.debug("No .env file found, using config.json only")
        else:
            # Même sans python-dotenv, on peut utiliser os.getenv pour les variables système
            logger.debug("python-dotenv not available, using system environment variables only")
    
    def _override_with_env(self):
        """
        Remplace les valeurs sensibles du config.json par celles des variables d'environnement
        Les variables d'environnement ont la priorité
        """
        # Mapping des chemins de config vers les noms de variables d'environnement
        env_mappings = {
            # Wallet
            ('wallet', 'address'): 'WALLET_ADDRESS',
            ('wallet', 'private_key'): 'WALLET_PRIVATE_KEY',
            
            # Extended - toutes les clés sensibles
            ('exchanges', 'extended', 'api_key'): 'EXTENDED_API_KEY',
            ('exchanges', 'extended', 'public_key'): 'EXTENDED_PUBLIC_KEY',
            ('exchanges', 'extended', 'private_key'): 'EXTENDED_PRIVATE_KEY',
            ('exchanges', 'extended', 'vault_id'): 'EXTENDED_VAULT_ID',
            
            # Hyperliquid (si nécessaire)
            ('exchanges', 'hyperliquid', 'api_key'): 'HYPERLIQUID_API_KEY',
            
            # Variational (si nécessaire)
            ('exchanges', 'variational', 'api_key'): 'VARIATIONAL_API_KEY',
        }
        
        # Mapping simplifié pour les variables d'environnement directes
        # Permet d'utiliser des noms plus courts si souhaité
        simple_env_mappings = {
            # Variables directes (sans préfixe)
            'ADDRESS': ('wallet', 'address'),
            'PRIVATE_KEY': ('wallet', 'private_key'),
            'API_KEY': ('exchanges', 'extended', 'api_key'),
            'PUBLIC_KEY': ('exchanges', 'extended', 'public_key'),
            'VAULT_ID': ('exchanges', 'extended', 'vault_id'),
        }
        
        # Traiter d'abord les mappings complets
        for config_path, env_var in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value:
                self._set_config_value(config_path, env_value, env_var)
        
        # Ensuite les mappings simplifiés (si les valeurs complètes n'existent pas)
        for env_var, config_path in simple_env_mappings.items():
            # Vérifier si la valeur complète n'a pas déjà été définie
            full_env_var = f"EXTENDED_{env_var}" if env_var in ['API_KEY', 'PUBLIC_KEY', 'VAULT_ID'] else f"WALLET_{env_var}"
            if not os.getenv(full_env_var):
                env_value = os.getenv(env_var)
                if env_value:
                    self._set_config_value(config_path, env_value, env_var)
    
    def _set_config_value(self, config_path: tuple, value: str, env_var: str):
        """
        Définit une valeur dans la configuration en naviguant dans la structure
        
        Args:
            config_path: Tuple représentant le chemin (ex: ('wallet', 'address'))
            value: Valeur à définir
            env_var: Nom de la variable d'environnement (pour le logging)
        """
        # Naviguer dans la structure de config
        current = self.config
        for key in config_path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Définir la valeur
        current[config_path[-1]] = value
        logger.debug(f"Overridden {'.'.join(config_path)} with environment variable {env_var}")
        
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
