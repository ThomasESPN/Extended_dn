"""
Trade Executor
Gère l'exécution des trades d'arbitrage sur Extended et Variational
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict
from enum import Enum
from loguru import logger


class PositionSide(Enum):
    """Côté de la position"""
    LONG = "long"
    SHORT = "short"


class OrderStatus(Enum):
    """Statut d'un ordre"""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Position:
    """Représente une position ouverte"""
    id: str
    symbol: str
    exchange: str
    side: PositionSide
    size: float
    entry_price: float
    opened_at: datetime
    status: OrderStatus = OrderStatus.OPEN
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    funding_collected: float = 0.0
    
    def to_dict(self) -> dict:
        """Convertit en dictionnaire"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'exchange': self.exchange,
            'side': self.side.value,
            'size': self.size,
            'entry_price': self.entry_price,
            'opened_at': self.opened_at.isoformat(),
            'status': self.status.value,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'exit_price': self.exit_price,
            'pnl': self.pnl,
            'funding_collected': self.funding_collected
        }


@dataclass
class ArbitragePair:
    """Paire de positions d'arbitrage (delta-neutral)"""
    id: str
    symbol: str
    long_position: Position
    short_position: Position
    opened_at: datetime
    strategy_type: str
    target_close_time: Optional[datetime] = None
    status: str = "active"
    total_funding: float = 0.0
    net_pnl: float = 0.0
    
    def is_delta_neutral(self) -> bool:
        """Vérifie si les positions sont bien delta-neutral"""
        return abs(self.long_position.size - self.short_position.size) < 0.01
    
    def update_pnl(self):
        """Met à jour le PnL total"""
        self.net_pnl = (
            self.long_position.pnl + 
            self.short_position.pnl +
            self.total_funding
        )


class TradeExecutor:
    """Exécuteur de trades pour l'arbitrage"""
    
    def __init__(self, config):
        """
        Initialise l'exécuteur
        
        Args:
            config: Configuration du bot
        """
        self.config = config
        self.active_pairs: Dict[str, ArbitragePair] = {}
        self.closed_pairs: Dict[str, ArbitragePair] = {}
        
        # TODO: Initialiser les connexions aux exchanges
        self.extended_client = None
        self.variational_client = None
        
    def open_arbitrage_pair(
        self,
        symbol: str,
        long_exchange: str,
        short_exchange: str,
        size: float,
        strategy_type: str,
        target_close_time: Optional[datetime] = None
    ) -> Optional[ArbitragePair]:
        """
        Ouvre une paire de positions d'arbitrage
        
        Args:
            symbol: Symbole de la paire
            long_exchange: Exchange pour la position long
            short_exchange: Exchange pour la position short
            size: Taille de la position
            strategy_type: Type de stratégie
            target_close_time: Heure cible de fermeture
            
        Returns:
            ArbitragePair créée ou None en cas d'échec
        """
        try:
            logger.info(f"Opening arbitrage pair for {symbol}")
            logger.info(f"  Long: {long_exchange}, Short: {short_exchange}, Size: ${size}")
            
            # Ouvrir la position long
            long_pos = self._open_position(
                symbol, long_exchange, PositionSide.LONG, size
            )
            
            if not long_pos:
                logger.error("Failed to open long position")
                return None
            
            # Ouvrir la position short
            short_pos = self._open_position(
                symbol, short_exchange, PositionSide.SHORT, size
            )
            
            if not short_pos:
                logger.error("Failed to open short position, closing long...")
                self._close_position(long_pos)
                return None
            
            # Vérifier que les prix sont similaires
            price_diff_pct = abs(long_pos.entry_price - short_pos.entry_price) / long_pos.entry_price
            if price_diff_pct > 0.005:  # 0.5% max
                logger.warning(f"Price difference too high: {price_diff_pct:.4%}")
            
            # Créer la paire d'arbitrage
            pair_id = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            arb_pair = ArbitragePair(
                id=pair_id,
                symbol=symbol,
                long_position=long_pos,
                short_position=short_pos,
                opened_at=datetime.now(),
                strategy_type=strategy_type,
                target_close_time=target_close_time
            )
            
            self.active_pairs[pair_id] = arb_pair
            
            logger.success(f"Arbitrage pair opened: {pair_id}")
            logger.info(f"  Long price: ${long_pos.entry_price}")
            logger.info(f"  Short price: ${short_pos.entry_price}")
            
            return arb_pair
            
        except Exception as e:
            logger.error(f"Error opening arbitrage pair: {e}")
            return None
    
    def close_arbitrage_pair(self, pair_id: str) -> bool:
        """
        Ferme une paire d'arbitrage
        
        Args:
            pair_id: ID de la paire
            
        Returns:
            True si succès
        """
        if pair_id not in self.active_pairs:
            logger.error(f"Arbitrage pair {pair_id} not found")
            return False
        
        pair = self.active_pairs[pair_id]
        
        try:
            logger.info(f"Closing arbitrage pair {pair_id}")
            
            # Fermer les deux positions
            long_closed = self._close_position(pair.long_position)
            short_closed = self._close_position(pair.short_position)
            
            if long_closed and short_closed:
                pair.status = "closed"
                pair.update_pnl()
                
                # Déplacer vers les paires fermées
                self.closed_pairs[pair_id] = pair
                del self.active_pairs[pair_id]
                
                logger.success(f"Arbitrage pair closed: {pair_id}")
                logger.info(f"  Net PnL: ${pair.net_pnl:.4f}")
                logger.info(f"  Total funding: ${pair.total_funding:.4f}")
                
                return True
            else:
                logger.error("Failed to close one or both positions")
                return False
                
        except Exception as e:
            logger.error(f"Error closing arbitrage pair: {e}")
            return False
    
    def _open_position(
        self,
        symbol: str,
        exchange: str,
        side: PositionSide,
        size: float
    ) -> Optional[Position]:
        """
        Ouvre une position sur un exchange
        
        TODO: Implémenter l'API réelle des exchanges
        """
        try:
            # Simulation pour le développement
            logger.debug(f"Opening {side.value} position on {exchange} for {symbol}")
            
            # TODO: Appel API réel
            # if exchange == "Extended":
            #     order = self.extended_client.create_order(...)
            # elif exchange == "Variational":
            #     order = self.variational_client.create_order(...)
            
            # Simulation
            import random
            entry_price = 100000 + random.uniform(-100, 100)  # BTC price simulation
            
            position = Position(
                id=f"{exchange}_{symbol}_{side.value}_{datetime.now().timestamp()}",
                symbol=symbol,
                exchange=exchange,
                side=side,
                size=size,
                entry_price=entry_price,
                opened_at=datetime.now()
            )
            
            logger.debug(f"Position opened: {position.id} at ${entry_price}")
            return position
            
        except Exception as e:
            logger.error(f"Error opening position: {e}")
            return None
    
    def _close_position(self, position: Position) -> bool:
        """
        Ferme une position
        
        TODO: Implémenter l'API réelle des exchanges
        """
        try:
            logger.debug(f"Closing position {position.id}")
            
            # TODO: Appel API réel
            
            # Simulation
            import random
            exit_price = position.entry_price + random.uniform(-50, 50)
            
            # Calculer le PnL
            if position.side == PositionSide.LONG:
                pnl = (exit_price - position.entry_price) * (position.size / position.entry_price)
            else:
                pnl = (position.entry_price - exit_price) * (position.size / position.entry_price)
            
            position.exit_price = exit_price
            position.closed_at = datetime.now()
            position.status = OrderStatus.CLOSED
            position.pnl = pnl
            
            logger.debug(f"Position closed: {position.id}, PnL: ${pnl:.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
    
    def get_active_pairs(self) -> Dict[str, ArbitragePair]:
        """Retourne les paires actives"""
        return self.active_pairs
    
    def update_funding_collected(self, pair_id: str, amount: float, exchange: str):
        """
        Met à jour le funding collecté pour une paire
        
        Args:
            pair_id: ID de la paire
            amount: Montant du funding (positif = reçu, négatif = payé)
            exchange: Exchange concerné
        """
        if pair_id in self.active_pairs:
            pair = self.active_pairs[pair_id]
            
            # Ajouter au funding de la position concernée
            if pair.long_position.exchange == exchange:
                pair.long_position.funding_collected += amount
            elif pair.short_position.exchange == exchange:
                pair.short_position.funding_collected += amount
            
            # Mettre à jour le total
            pair.total_funding = (
                pair.long_position.funding_collected +
                pair.short_position.funding_collected
            )
            
            logger.debug(f"Updated funding for {pair_id}: ${amount:.4f} from {exchange}")
