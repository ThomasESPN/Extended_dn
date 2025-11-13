"""
Funding Rate Data Collector
Récupère les funding rates en temps réel depuis Extended et Variational
Utilise l'API Loris Tools pour les données en temps réel
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import time
from loguru import logger
import requests
from .loris_api import get_loris_api


@dataclass
class FundingRate:
    """Données d'un funding rate"""
    exchange: str
    symbol: str
    rate: float
    timestamp: datetime
    next_funding_time: Optional[datetime] = None
    funding_interval: int = 3600  # en secondes


class FundingCollector:
    """Collecteur de funding rates"""
    
    def __init__(self, config):
        """
        Initialise le collecteur
        
        Args:
            config: Configuration du bot
        """
        self.config = config
        self.cache: Dict[str, FundingRate] = {}
        self.cache_duration = 60  # secondes
        self.loris = get_loris_api()  # Client API Loris Tools
        
    def get_extended_funding(self, symbol: str) -> Optional[FundingRate]:
        """
        Récupère le funding rate Extended pour un symbole
        
        Args:
            symbol: Symbole de la paire (ex: BTC/USDT)
            
        Returns:
            FundingRate ou None
        """
        cache_key = f"extended_{symbol}"
        
        # Vérifier le cache
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if (datetime.now() - cached.timestamp).seconds < self.cache_duration:
                return cached
        
        try:
            # TODO: Remplacer par l'API réelle Extended
            # Pour l'instant, simulation
            rate = self._fetch_extended_funding(symbol)
            
            if rate is not None:
                funding = FundingRate(
                    exchange="Extended",
                    symbol=symbol,
                    rate=rate,
                    timestamp=datetime.now(),
                    funding_interval=3600,
                    next_funding_time=self._get_next_hour()
                )
                self.cache[cache_key] = funding
                return funding
                
        except Exception as e:
            logger.error(f"Error fetching Extended funding for {symbol}: {e}")
        
        return None
    
    def get_variational_funding(self, symbol: str) -> Optional[FundingRate]:
        """
        Récupère le funding rate Variational pour un symbole
        
        Args:
            symbol: Symbole de la paire (ex: BTC/USDT)
            
        Returns:
            FundingRate ou None
        """
        cache_key = f"variational_{symbol}"
        
        # Vérifier le cache
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if (datetime.now() - cached.timestamp).seconds < self.cache_duration:
                return cached
        
        try:
            # TODO: Remplacer par l'API réelle Variational
            rate = self._fetch_variational_funding(symbol)
            
            if rate is not None:
                # Récupérer l'intervalle spécifique à la paire
                interval = self._get_variational_interval(symbol)
                
                funding = FundingRate(
                    exchange="Variational",
                    symbol=symbol,
                    rate=rate,
                    timestamp=datetime.now(),
                    funding_interval=interval,
                    next_funding_time=self._get_next_variational_time(interval)
                )
                self.cache[cache_key] = funding
                return funding
                
        except Exception as e:
            logger.error(f"Error fetching Variational funding for {symbol}: {e}")
        
        return None
    
    def get_all_funding_rates(self, symbols: List[str]) -> Dict[str, Dict[str, FundingRate]]:
        """
        Récupère tous les funding rates pour une liste de symboles
        
        Args:
            symbols: Liste des symboles
            
        Returns:
            Dict avec structure: {symbol: {exchange: FundingRate}}
        """
        results = {}
        
        for symbol in symbols:
            results[symbol] = {
                'extended': self.get_extended_funding(symbol),
                'variational': self.get_variational_funding(symbol)
            }
        
        return results
    
    def _fetch_extended_funding(self, symbol: str) -> Optional[float]:
        """
        Récupère le MEILLEUR funding 1h (Extended ou Hyperliquid)
        
        Cherche le meilleur rate parmi les exchanges 1h disponibles
        """
        logger.debug(f"Fetching best 1h funding for {symbol}")
        
        try:
            # Récupérer toutes les données Loris
            data = self.loris.fetch_all_funding_rates()
            if not data:
                logger.warning("Failed to fetch data from Loris API")
                return None
            
            # Convertir le symbole (BTC/USDT -> BTC)
            base_symbol = symbol.split('/')[0]
            
            # Vérifier si le symbole existe
            if base_symbol not in data.get('symbols', []):
                logger.warning(f"Symbol {base_symbol} not found in Loris data")
                return None
            
            # 🎯 Chercher le MEILLEUR parmi Extended et Hyperliquid
            exchanges_info = self.loris.get_exchange_info(data)
            
            best_rate = None
            best_exchange = None
            
            for exchange_name, info in exchanges_info.items():
                base_name = exchange_name.split('_')[0].lower()
                
                # Chercher parmi Extended et Hyperliquid
                if base_name in ['extended', 'hyperliquid']:
                    rate = self.loris.get_funding_rate(data, exchange_name, base_symbol)
                    if rate is not None:
                        logger.debug(f"{base_name.upper()} funding: {rate:.6f}")
                        # Prendre le meilleur (rate le plus négatif = on reçoit le plus)
                        if best_rate is None or rate < best_rate:
                            best_rate = rate
                            best_exchange = base_name.upper()
            
            if best_rate is not None:
                logger.debug(f"Best 1h funding for {base_symbol}: {best_exchange} @ {best_rate:.6f}")
                return best_rate
            
            logger.warning(f"No 1h funding found for {base_symbol}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching 1h funding for {symbol}: {e}")
            return None
    
    def _fetch_variational_funding(self, symbol: str) -> Optional[float]:
        """
        Récupère le funding depuis Variational UNIQUEMENT (via Loris Tools)
        
        Focus sur Variational uniquement, pas les autres exchanges 8h
        """
        logger.debug(f"Fetching Variational funding for {symbol}")
        
        try:
            # Récupérer toutes les données Loris
            data = self.loris.fetch_all_funding_rates()
            if not data:
                logger.warning("Failed to fetch data from Loris API")
                return None
            
            # Convertir le symbole (BTC/USDT -> BTC)
            base_symbol = symbol.split('/')[0]
            
            # Vérifier si le symbole existe
            if base_symbol not in data.get('symbols', []):
                logger.warning(f"Symbol {base_symbol} not found in Loris data")
                return None
            
            # ⚠️ FOCUS: Chercher UNIQUEMENT Variational
            exchanges_info = self.loris.get_exchange_info(data)
            
            for exchange_name, info in exchanges_info.items():
                if exchange_name.split('_')[0].lower() == 'variational':
                    rate = self.loris.get_funding_rate(data, exchange_name, base_symbol)
                    if rate is not None:
                        logger.debug(f"Variational funding for {base_symbol}: {rate:.6f}")
                        return rate
            
            logger.warning(f"Variational funding not found for {base_symbol}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Variational funding for {symbol}: {e}")
            return None
    
    def _get_variational_interval(self, symbol: str) -> int:
        """Récupère l'intervalle de funding Variational pour une paire"""
        base = symbol.split('/')[0]
        intervals = self.config.get('exchanges', 'variational', 'funding_intervals')
        return intervals.get(base, intervals.get('default', 28800))
    
    def _get_next_hour(self) -> datetime:
        """Calcule la prochaine heure ronde"""
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0)
        
        if now.minute > 0 or now.second > 0:
            next_hour = next_hour.replace(hour=now.hour + 1)
        
        return next_hour
    
    def _get_next_variational_time(self, interval: int) -> datetime:
        """
        Calcule le prochain temps de funding Variational
        
        Args:
            interval: Intervalle en secondes (3600, 14400, 28800)
        """
        now = datetime.now()
        
        # Pour 8h: 00:00, 08:00, 16:00
        if interval == 28800:  # 8 heures
            hours = [0, 8, 16]
            for hour in hours:
                next_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if next_time > now:
                    return next_time
            # Si aucun trouvé, prendre le premier du lendemain
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Pour les autres intervalles, calculer simplement
        return self._get_next_hour()
    
    def clear_cache(self):
        """Vide le cache des funding rates"""
        self.cache.clear()
        logger.debug("Funding rate cache cleared")
