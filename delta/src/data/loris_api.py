"""
Loris Tools API Integration
Récupère les funding rates en temps réel depuis https://api.loris.tools/funding

API Documentation: https://loris.tools/api-docs
Note: Les rates sont multipliés par 10,000 (ex: 25 = 0.0025 = 0.25%)
Note: Extended, Hyperliquid, Lighter, Vest utilisent des intervalles de 1h (rates multipliés par 8)
"""
import requests
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
from dataclasses import dataclass


@dataclass
class LorisExchangeInfo:
    """Information sur un exchange depuis Loris Tools"""
    name: str  # ex: "binance_1_perp"
    display: str  # ex: "BINANCE"
    interval: int  # Intervalle de funding en secondes (3600 ou 28800)


class LorisAPI:
    """Client pour l'API Loris Tools"""
    
    API_URL = "https://api.loris.tools/funding"
    
    # Exchanges avec intervalle de 1h (rates multipliés par 8 par l'API)
    HOURLY_EXCHANGES = [
        "extended", "hyperliquid", "lighter", "vest"
    ]
    
    def __init__(self):
        """Initialise le client API"""
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'TimingFundingArbitrage/1.0'
        })
        self.cache = None
        self.cache_timestamp = None
        self.cache_duration = 60  # L'API se met à jour toutes les 60 secondes
        
    def fetch_all_funding_rates(self) -> Optional[Dict]:
        """
        Récupère tous les funding rates depuis l'API
        
        Returns:
            Dict avec la structure complète de l'API ou None en cas d'erreur
        """
        # Vérifier le cache
        if self.cache and self.cache_timestamp:
            elapsed = (datetime.now() - self.cache_timestamp).seconds
            if elapsed < self.cache_duration:
                logger.debug(f"Using cached Loris data ({elapsed}s old)")
                return self.cache
        
        try:
            logger.debug(f"Fetching funding rates from {self.API_URL}")
            response = self.session.get(self.API_URL, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Mettre en cache
            self.cache = data
            self.cache_timestamp = datetime.now()
            
            logger.info(f"Fetched {len(data.get('symbols', []))} symbols from Loris Tools")
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching from Loris API: {e}")
            return None
    
    def get_exchange_info(self, data: Dict) -> Dict[str, LorisExchangeInfo]:
        """
        Parse les informations des exchanges
        
        Args:
            data: Réponse de l'API Loris
            
        Returns:
            Dict {exchange_name: LorisExchangeInfo}
        """
        exchanges = {}
        
        for exchange in data.get('exchanges', {}).get('exchange_names', []):
            name = exchange['name']
            display = exchange['display']
            
            # Déterminer l'intervalle de funding
            # Extended, Hyperliquid, Lighter, Vest = 1h (3600s)
            # Autres = 8h (28800s)
            base_name = name.split('_')[0].lower()
            interval = 3600 if base_name in self.HOURLY_EXCHANGES else 28800
            
            exchanges[name] = LorisExchangeInfo(
                name=name,
                display=display,
                interval=interval
            )
        
        return exchanges
    
    def get_funding_rate(self, data: Dict, exchange: str, symbol: str) -> Optional[float]:
        """
        Récupère le funding rate pour un exchange et symbole spécifique
        
        Args:
            data: Réponse de l'API Loris
            exchange: Nom de l'exchange (ex: "binance_1_perp")
            symbol: Symbole normalisé (ex: "BTC")
            
        Returns:
            Funding rate en décimal (ex: 0.0025) ou None
        """
        try:
            funding_rates = data.get('funding_rates', {})
            
            # Récupérer le rate (multiplié par 10,000 par l'API)
            rate_scaled = funding_rates.get(exchange, {}).get(symbol)
            
            if rate_scaled is None:
                return None
            
            # Convertir en décimal (diviser par 10,000)
            rate = rate_scaled / 10000.0
            
            return rate
            
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Error parsing funding rate for {exchange}/{symbol}: {e}")
            return None
    
    def find_best_arbitrage(self, symbol: str) -> Optional[Dict]:
        """
        Trouve la meilleure opportunité d'arbitrage pour un symbole
        Cherche le MEILLEUR rate 1h (Extended ou Hyperliquid) vs MEILLEUR rate 8h (Variational)
        
        Args:
            symbol: Symbole normalisé (ex: "BTC")
            
        Returns:
            Dict avec les détails de l'arbitrage ou None
        """
        data = self.fetch_all_funding_rates()
        if not data:
            return None
        
        exchanges_info = self.get_exchange_info(data)
        
        # 🎯 Chercher le MEILLEUR rate parmi les exchanges 1h (Extended, Hyperliquid)
        best_1h_rate = None
        best_1h_exchange = None
        
        # 🎯 Chercher le rate Variational (8h)
        variational_rate = None
        variational_exchange = None
        
        for exchange_name, info in exchanges_info.items():
            base_name = exchange_name.split('_')[0].lower()
            
            # Exchanges 1h (Extended, Hyperliquid, Lighter, Vest)
            if base_name in ['extended', 'hyperliquid']:
                rate = self.get_funding_rate(data, exchange_name, symbol)
                if rate is not None:
                    logger.debug(f"{base_name.upper()} (1h) rate for {symbol}: {rate:.6f}")
                    # Prendre le rate le plus bas (négatif = on reçoit)
                    if best_1h_rate is None or rate < best_1h_rate:
                        best_1h_rate = rate
                        best_1h_exchange = base_name.upper()
            
            # Variational (8h)
            elif base_name == 'variational':
                variational_rate = self.get_funding_rate(data, exchange_name, symbol)
                variational_exchange = "VARIATIONAL"
                if variational_rate is not None:
                    logger.debug(f"Variational (8h) rate for {symbol}: {variational_rate:.6f}")
        
        # Vérifier qu'on a les deux rates
        if best_1h_rate is None or variational_rate is None:
            logger.warning(f"Missing rates for {symbol} - 1h: {best_1h_rate}, 8h: {variational_rate}")
            return None
        
        # Calculer le spread
        spread = abs(best_1h_rate - variational_rate)
        
        logger.debug(f"Best arbitrage for {symbol}: {best_1h_exchange} ({best_1h_rate:.6f}) vs {variational_exchange} ({variational_rate:.6f})")
        
        return {
            'symbol': symbol,
            'best_1h_rate': best_1h_rate,
            'best_1h_exchange': best_1h_exchange,
            'variational_rate': variational_rate,
            'variational_exchange': variational_exchange,
            'spread': spread,
            'timestamp': data.get('timestamp')
        }
    
    def get_all_symbols(self) -> List[str]:
        """
        Récupère la liste de tous les symboles disponibles
        
        Returns:
            Liste des symboles
        """
        data = self.fetch_all_funding_rates()
        if not data:
            return []
        
        return data.get('symbols', [])
    
    def get_extended_like_exchanges(self, data: Dict = None) -> List[str]:
        """
        Retourne UNIQUEMENT l'exchange Extended
        
        Returns:
            Liste avec Extended uniquement
        """
        if data is None:
            data = self.fetch_all_funding_rates()
            if not data:
                return []
        
        exchanges_info = self.get_exchange_info(data)
        return [
            name for name, info in exchanges_info.items()
            if name.split('_')[0].lower() == 'extended'
        ]
    
    def get_variational_like_exchanges(self, data: Dict = None) -> List[str]:
        """
        Retourne UNIQUEMENT l'exchange Variational
        
        Returns:
            Liste avec Variational uniquement
        """
        if data is None:
            data = self.fetch_all_funding_rates()
            if not data:
                return []
        
        exchanges_info = self.get_exchange_info(data)
        return [
            name for name, info in exchanges_info.items()
            if name.split('_')[0].lower() == 'variational'
        ]


# Instance singleton
_loris_api = None


def get_loris_api() -> LorisAPI:
    """Retourne l'instance singleton de LorisAPI"""
    global _loris_api
    if _loris_api is None:
        _loris_api = LorisAPI()
    return _loris_api
