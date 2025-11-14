"""
Arbitrage Strategy Calculator
Calcule la rentabilité des différentes stratégies d'arbitrage de funding
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger

from ..data.funding_collector import FundingRate


@dataclass
class ArbitrageOpportunity:
    """Opportunité d'arbitrage identifiée"""
    symbol: str
    extended_rate: float
    variational_rate: float
    position_type: str  # 'standard', 'both_positive', 'both_negative', 'avoid_variational'
    long_exchange: str
    short_exchange: str
    estimated_profit_full_cycle: float
    estimated_profit_early_close: float
    recommended_strategy: str
    profit_per_hour: float
    risk_level: str
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire"""
        return {
            'symbol': self.symbol,
            'extended_rate': self.extended_rate,
            'variational_rate': self.variational_rate,
            'position_type': self.position_type,
            'long_exchange': self.long_exchange,
            'short_exchange': self.short_exchange,
            'estimated_profit_full_cycle': self.estimated_profit_full_cycle,
            'estimated_profit_early_close': self.estimated_profit_early_close,
            'recommended_strategy': self.recommended_strategy,
            'profit_per_hour': self.profit_per_hour,
            'risk_level': self.risk_level
        }


class ArbitrageCalculator:
    """Calculateur de stratégies d'arbitrage de funding"""
    
    def __init__(self, config):
        """
        Initialise le calculateur
        
        Args:
            config: Configuration du bot
        """
        self.config = config
        self.position_size = config.get('trading', 'max_position_size', default=10000)
        self.min_profit_threshold = config.get('trading', 'min_profit_threshold', default=0.0001)
        
    def calculate_funding_payment(self, size: float, rate: float) -> float:
        """
        Calcule le paiement de funding
        
        Args:
            size: Taille de la position en USD
            rate: Taux de funding (ex: 0.0013)
            
        Returns:
            Montant du paiement en USD
        """
        # Formula: Size × (funding_rate / 100)
        # Mais si le rate est déjà en pourcentage décimal (0.0013 = 0.13%)
        # alors: Size × funding_rate
        payment = size * rate
        return round(payment, 4)
    
    def analyze_opportunity(
        self, 
        symbol: str,
        extended_funding: FundingRate,
        variational_funding: FundingRate,
        position_size: Optional[float] = None
    ) -> Optional[ArbitrageOpportunity]:
        """
        Analyse une opportunité d'arbitrage
        
        Args:
            symbol: Symbole de la paire
            extended_funding: Funding rate Extended
            variational_funding: Funding rate Variational
            position_size: Taille de position (optionnel)
            
        Returns:
            ArbitrageOpportunity ou None si non rentable
        """
        if position_size is None:
            position_size = self.position_size
        
        ext_rate = extended_funding.rate
        var_rate = variational_funding.rate
        
        # Calculer les paiements
        ext_payment = self.calculate_funding_payment(position_size, abs(ext_rate))
        var_payment = self.calculate_funding_payment(position_size, abs(var_rate))
        
        # Déterminer la stratégie selon les polarités
        opportunity = self._determine_strategy(
            symbol, ext_rate, var_rate, ext_payment, var_payment,
            extended_funding.funding_interval, variational_funding.funding_interval
        )
        
        # Vérifier si l'opportunité est rentable
        if opportunity and opportunity.estimated_profit_full_cycle > 0:
            return opportunity
        
        return None
    
    def _determine_strategy(
        self,
        symbol: str,
        ext_rate: float,
        var_rate: float,
        ext_payment: float,
        var_payment: float,
        ext_interval: int,
        var_interval: int
    ) -> Optional[ArbitrageOpportunity]:
        """
        Détermine la meilleure stratégie selon les taux de funding
        
        Returns:
            ArbitrageOpportunity avec la stratégie recommandée
        """
        # Cas 1: Extended positif, Variational positif (standard)
        if ext_rate > 0 and var_rate > 0:
            return self._strategy_standard(
                symbol, ext_rate, var_rate, ext_payment, var_payment,
                ext_interval, var_interval
            )
        
        # Cas 2: Extended négatif, Variational positif (both receive)
        elif ext_rate < 0 and var_rate > 0:
            return self._strategy_both_positive(
                symbol, ext_rate, var_rate, ext_payment, var_payment,
                ext_interval, var_interval
            )
        
        # Cas 3: Extended négatif, Variational négatif (avoid variational)
        elif ext_rate < 0 and var_rate < 0:
            return self._strategy_both_negative(
                symbol, ext_rate, var_rate, ext_payment, var_payment,
                ext_interval, var_interval
            )
        
        # Cas 4: Extended positif, Variational négatif
        elif ext_rate > 0 and var_rate < 0:
            return self._strategy_mixed(
                symbol, ext_rate, var_rate, ext_payment, var_payment,
                ext_interval, var_interval
            )
        
        return None
    
    def _strategy_standard(
        self, symbol, ext_rate, var_rate, ext_payment, var_payment,
        ext_interval, var_interval
    ) -> ArbitrageOpportunity:
        """
        Stratégie standard: Short Extended, Long Variational
        - On reçoit le funding Extended (positif)
        - On paye le funding Variational (positif)
        """
        # Nombre de paiements Extended dans un cycle Variational
        num_ext_payments = var_interval // ext_interval
        
        # Profit cycle complet (avec paiement Variational)
        profit_full = (ext_payment * num_ext_payments) - var_payment
        
        # Profit fermeture anticipée (sans paiement Variational)
        profit_early = ext_payment * (num_ext_payments - 1)
        
        # Recommandation
        if profit_full > profit_early:
            strategy = "full_cycle"
            recommended_profit = profit_full
        else:
            strategy = "early_close"
            recommended_profit = profit_early
        
        return ArbitrageOpportunity(
            symbol=symbol,
            extended_rate=ext_rate,
            variational_rate=var_rate,
            position_type="standard",
            long_exchange="Variational",
            short_exchange="Extended",
            estimated_profit_full_cycle=profit_full,
            estimated_profit_early_close=profit_early,
            recommended_strategy=strategy,
            profit_per_hour=recommended_profit / (var_interval / 3600),
            risk_level="low"
        )
    
    def _strategy_both_positive(
        self, symbol, ext_rate, var_rate, ext_payment, var_payment,
        ext_interval, var_interval
    ) -> ArbitrageOpportunity:
        """
        Stratégie both positive: Long Extended, Short Variational
        - On reçoit le funding Extended (négatif -> on reçoit)
        - On reçoit le funding Variational (positif -> short reçoit)
        """
        num_ext_payments = var_interval // ext_interval
        
        # Les deux sont des revenus!
        profit_full = (ext_payment * num_ext_payments) + var_payment
        
        return ArbitrageOpportunity(
            symbol=symbol,
            extended_rate=ext_rate,
            variational_rate=var_rate,
            position_type="both_positive",
            long_exchange="Extended",
            short_exchange="Variational",
            estimated_profit_full_cycle=profit_full,
            estimated_profit_early_close=ext_payment * num_ext_payments,
            recommended_strategy="full_cycle",
            profit_per_hour=profit_full / (var_interval / 3600),
            risk_level="very_low"
        )
    
    def _strategy_both_negative(
        self, symbol, ext_rate, var_rate, ext_payment, var_payment,
        ext_interval, var_interval
    ) -> ArbitrageOpportunity:
        """
        Stratégie both negative: Long Extended, Short Variational
        Fermer avant le paiement Variational
        """
        num_ext_payments = var_interval // ext_interval
        
        # Recevoir Extended mais éviter Variational
        profit_early = ext_payment * (num_ext_payments - 1)
        profit_full = (ext_payment * num_ext_payments) - var_payment
        
        return ArbitrageOpportunity(
            symbol=symbol,
            extended_rate=ext_rate,
            variational_rate=var_rate,
            position_type="both_negative",
            long_exchange="Extended",
            short_exchange="Variational",
            estimated_profit_full_cycle=profit_full,
            estimated_profit_early_close=profit_early,
            recommended_strategy="early_close",
            profit_per_hour=profit_early / ((var_interval - 3600) / 3600),
            risk_level="medium"
        )
    
    def _strategy_mixed(
        self, symbol, ext_rate, var_rate, ext_payment, var_payment,
        ext_interval, var_interval
    ) -> ArbitrageOpportunity:
        """
        Stratégie mixte: Extended positif, Variational négatif
        """
        num_ext_payments = var_interval // ext_interval
        
        # On reçoit Extended et Variational (car var négatif et on est short)
        profit_full = (ext_payment * num_ext_payments) + var_payment
        
        return ArbitrageOpportunity(
            symbol=symbol,
            extended_rate=ext_rate,
            variational_rate=var_rate,
            position_type="mixed",
            long_exchange="Variational",
            short_exchange="Extended",
            estimated_profit_full_cycle=profit_full,
            estimated_profit_early_close=ext_payment * num_ext_payments,
            recommended_strategy="full_cycle",
            profit_per_hour=profit_full / (var_interval / 3600),
            risk_level="low"
        )
    
    def find_best_opportunities(
        self,
        funding_data: Dict[str, Dict[str, FundingRate]]
    ) -> List[ArbitrageOpportunity]:
        """
        Trouve les meilleures opportunités d'arbitrage
        
        Args:
            funding_data: Dict {symbol: {exchange: FundingRate}}
            
        Returns:
            Liste d'opportunités triées par rentabilité
        """
        opportunities = []
        
        for symbol, rates in funding_data.items():
            ext_funding = rates.get('extended')
            var_funding = rates.get('variational')
            
            if ext_funding and var_funding:
                opp = self.analyze_opportunity(symbol, ext_funding, var_funding)
                if opp:
                    opportunities.append(opp)
        
        # Trier par profit par heure (décroissant)
        opportunities.sort(key=lambda x: x.profit_per_hour, reverse=True)
        
        return opportunities
