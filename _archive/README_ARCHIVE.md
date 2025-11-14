# 📦 Archive - Anciens Fichiers

Ce dossier contient les fichiers obsolètes ou redondants qui ont été nettoyés du projet principal.

## 📂 Structure

### `old_tests/`
Anciens fichiers de test remplacés par les scripts actuels :
- `test_bot.py`, `test_bot_v2.py` → Remplacés par `test_bot_auto.py`
- `test_hyperliquid_api.py`, `test_hyperliquid_funding.py` → Intégrés dans `src/exchanges/`
- `test_monitoring.py`, `test_sniper.py`, `test_timing.py` → Non utilisés
- `test_wallet_setup.py`, `test_explication.py` → Tests one-shot obsolètes

### `old_scripts/`
Scripts de développement/debug obsolètes :
- `main_extended_hyperliquid.py`, `main_extended_hyperliquid_v2.py` → Remplacés par `src/main.py`
- `main_old.py` → Ancienne version du bot principal
- `debug_*.py` → Scripts de debugging temporaires
- `check_*.py`, `compare_*.py` → Scripts d'analyse one-shot
- `explain_calculs*.py` → Scripts d'explication temporaires
- `find_best_like_loris.py`, `find_extended_hyperliquid.py` → Remplacés par `find_best_opportunity.py`

### `old_docs/`
Documentation redondante ou obsolète :
- `README_OLD.md` → Ancienne version du README
- `EXPLICATION_CALCULS.md`, `FOCUS_EXTENDED_VARIATIONAL.md` → Explications techniques détaillées
- `GUIDE_FUNDING_ARBITRAGE.md`, `TIMING_FUNDING.md` → Guides techniques
- `LORIS_INTEGRATION.md`, `REPONSE_COMPLETE.md` → Documentation d'intégration
- `SIMPLE_WALLET_GUIDE.md`, `STRATEGIE_SNIPER.md` → Guides spécifiques
- `VERIFICATION_PDF.md` → Vérification temporaire
- `SYNTHESE.txt` → Synthèse de développement

## ♻️ Pourquoi ces fichiers sont archivés ?

Ces fichiers ont été déplacés pour :
1. **Simplifier la structure** du projet
2. **Réduire la confusion** entre anciens et nouveaux fichiers
3. **Garder l'historique** sans encombrer le workspace
4. **Améliorer la maintenance** du code actif

## 🔄 Restauration

Si vous avez besoin d'un fichier archivé :

```powershell
# Exemple : restaurer un test
Move-Item _archive\old_tests\test_xyz.py .
```

---

**Note**: Ces fichiers peuvent être supprimés définitivement après vérification que tout fonctionne correctement avec la nouvelle structure.

*Archive créée le: 14 Novembre 2025*
