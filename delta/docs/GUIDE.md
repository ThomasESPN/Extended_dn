# Guide d'utilisation - Timing Funding Arbitrage Bot

## 🚀 Démarrage rapide

### 1. Installation

```bash
# Cloner ou télécharger le projet dans c:\Users\wowo\Desktop\delta

# Installer les dépendances
pip install -r requirements.txt
```

### 2. Configuration

Éditer le fichier `config/config.json` (copié depuis `config.example.json`) :

```json
{
  "exchanges": {
    "extended": {
      "api_key": "VOTRE_CLE_API_EXTENDED",
      "api_secret": "VOTRE_SECRET_API_EXTENDED"
    },
    "variational": {
      "api_key": "VOTRE_CLE_API_VARIATIONAL",
      "api_secret": "VOTRE_SECRET_API_VARIATIONAL"
    }
  }
}
```

### 3. Tester le système

```bash
# Exemple rapide
python examples/quick_start.py

# Analyser les opportunités
python src/analyzer.py

# Lancer le dashboard
python src/dashboard.py
```

## 📊 Fonctionnalités principales

### Analyser les opportunités

```bash
python src/analyzer.py
```

Affiche :
- Les funding rates actuels
- Les opportunités d'arbitrage
- Les profits estimés
- Les stratégies recommandées

### Lancer le bot en mode automatique

```bash
python src/main.py
```

Le bot va :
- Surveiller les funding rates en continu
- Ouvrir des positions selon les opportunités
- Fermer les positions au bon moment
- Gérer le rebalancing automatique

### Visualiser le dashboard

```bash
python src/dashboard.py
```

Accessible sur http://localhost:8050

Affiche :
- Opportunités en temps réel
- Positions actives
- Balances des exchanges
- Graphiques des funding rates

## 🎯 Stratégies implémentées

### 1. Standard (Funding positifs)
- **Short** sur Extended (funding positif)
- **Long** sur Variational (funding positif)
- Recevoir Extended, payer Variational
- Fermer avant 8h si plus rentable

### 2. Both Positive (Extended négatif, Variational positif)
- **Long** sur Extended (recevoir le funding négatif)
- **Short** sur Variational (recevoir le funding positif)
- **Double revenu** : recevoir des deux côtés
- Garder tout le cycle

### 3. Both Negative (Les deux négatifs)
- **Long** sur Extended
- **Short** sur Variational
- **Fermer avant 8h** pour éviter le paiement Variational
- Recevoir uniquement Extended

### 4. Mixed (Extended positif, Variational négatif)
- **Short** sur Extended
- **Long** sur Variational
- Double revenu (extended positif + variational négatif)

## ⚙️ Configuration avancée

### Paramètres de trading

```json
{
  "trading": {
    "min_profit_threshold": 0.0001,    // Profit minimum requis
    "max_position_size": 10000,        // Taille max par position
    "preferred_margin": 0.2,           // Marge préférée (20%)
    "max_leverage": 5,                 // Levier maximum
    "use_tp_sl": true,                // Activer TP/SL
    "tp_percentage": 0.5,             // Take Profit à 0.5%
    "sl_percentage": 1.0              // Stop Loss à 1%
  }
}
```

### Paramètres d'arbitrage

```json
{
  "arbitrage": {
    "check_interval": 60,                      // Vérifier toutes les 60s
    "min_funding_difference": 0.0001,          // Différence minimum
    "close_before_variational_funding": 300,   // Fermer 5min avant
    "watch_polarity_change": true,             // Surveiller changements
    "auto_rebalance": true,                    // Rebalancing auto
    "rebalance_threshold": 0.1                 // Seuil 10%
  }
}
```

## 📝 Exemple de calcul

### Données
- Funding Extended: 0.0013 (positif)
- Funding Variational: 0.0015 (positif)
- Position: $10,000
- Cycle: 8 heures

### Calculs

**Paiement Extended (par heure):**
```
10,000 × 0.0013 = $0.13
```

**Paiement Variational (par 8h):**
```
10,000 × 0.0015 = $0.15
```

**Profit cycle complet (8h):**
```
(0.13 × 8) - 0.15 = $0.89
```

**Profit fermeture anticipée (7h):**
```
0.13 × 7 = $0.91
```

✅ **Recommandation**: Fermeture anticipée (+$0.02)

## 🛡️ Sécurité

1. **Delta-Neutral**: Pas de risque directionnel
2. **TP/SL**: Protection contre les mouvements brusques
3. **Surveillance polarité**: Alerte si funding change de signe
4. **Marge importante**: Éviter les liquidations
5. **Rebalancing**: Maintenir l'équilibre entre exchanges

## 🔍 Monitoring

### Logs

Les logs sont stockés dans `logs/` :
- Un fichier par jour
- Rétention de 30 jours
- Niveaux: DEBUG, INFO, WARNING, ERROR

### Dashboard

Accès en temps réel à :
- Opportunités actuelles
- Positions ouvertes
- Performance
- Balances

## ⚠️ Points d'attention

1. **Vérifier les intervalles**: Les paires Variational ont des intervalles différents
2. **Frais de trading**: Inclure dans les calculs
3. **Slippage**: Tenir compte lors des ouvertures
4. **Liquidité**: Vérifier avant d'ouvrir de grosses positions
5. **API limits**: Respecter les limites des exchanges

## 🔗 Ressources

- Funding rates en direct: https://loris.tools
- Documentation Extended: [À compléter]
- Documentation Variational: [À compléter]

## 📞 Support

Pour toute question ou problème, consultez les logs dans `logs/` ou activez le mode DEBUG dans la configuration.
