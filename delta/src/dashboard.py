"""
Dashboard Web
Interface de monitoring pour le bot d'arbitrage
"""
import sys
from pathlib import Path
from datetime import datetime
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objs as go
from dash import dash_table

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from src.data import FundingCollector
from src.strategies import ArbitrageCalculator
from src.execution import TradeExecutor, RebalancingManager


class ArbitrageDashboard:
    """Dashboard de monitoring"""
    
    def __init__(self):
        """Initialise le dashboard"""
        self.config = get_config()
        self.collector = FundingCollector(self.config)
        self.calculator = ArbitrageCalculator(self.config)
        self.executor = TradeExecutor(self.config)
        self.rebalancer = RebalancingManager(self.config)
        
        # Créer l'app Dash
        self.app = dash.Dash(__name__, suppress_callback_exceptions=True)
        self.setup_layout()
        self.setup_callbacks()
    
    def setup_layout(self):
        """Configure le layout du dashboard"""
        self.app.layout = html.Div([
            html.Div([
                html.H1("🚀 Timing Funding Arbitrage Dashboard", 
                       style={'textAlign': 'center', 'color': '#2c3e50'}),
                html.Hr(),
            ]),
            
            # Interval pour refresh automatique
            dcc.Interval(
                id='interval-component',
                interval=30*1000,  # 30 secondes
                n_intervals=0
            ),
            
            # Section: Opportunités
            html.Div([
                html.H2("📊 Opportunités d'Arbitrage", style={'color': '#34495e'}),
                html.Div(id='opportunities-table'),
                html.Br(),
            ]),
            
            # Section: Positions actives
            html.Div([
                html.H2("💼 Positions Actives", style={'color': '#34495e'}),
                html.Div(id='positions-table'),
                html.Br(),
            ]),
            
            # Section: Balances
            html.Div([
                html.H2("💰 Balances", style={'color': '#34495e'}),
                html.Div(id='balances-info'),
                html.Br(),
            ]),
            
            # Section: Graphiques
            html.Div([
                html.H2("📈 Évolution des Funding Rates", style={'color': '#34495e'}),
                dcc.Graph(id='funding-chart'),
            ]),
            
            # Footer
            html.Hr(),
            html.Div([
                html.P(f"Dernière mise à jour: ", id='last-update',
                      style={'textAlign': 'center', 'color': '#7f8c8d'}),
            ]),
        ], style={'padding': '20px', 'fontFamily': 'Arial, sans-serif'})
    
    def setup_callbacks(self):
        """Configure les callbacks"""
        
        @self.app.callback(
            [Output('opportunities-table', 'children'),
             Output('positions-table', 'children'),
             Output('balances-info', 'children'),
             Output('funding-chart', 'figure'),
             Output('last-update', 'children')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_dashboard(n):
            """Met à jour tout le dashboard"""
            # Récupérer les données
            pairs = self.config.get_pairs()
            funding_data = self.collector.get_all_funding_rates(pairs)
            opportunities = self.calculator.find_best_opportunities(funding_data)
            
            # Table des opportunités
            opp_table = self.create_opportunities_table(opportunities)
            
            # Table des positions
            positions_table = self.create_positions_table()
            
            # Info balances
            balances_info = self.create_balances_info()
            
            # Graphique
            chart = self.create_funding_chart(funding_data)
            
            # Timestamp
            timestamp = f"Dernière mise à jour: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            return opp_table, positions_table, balances_info, chart, timestamp
    
    def create_opportunities_table(self, opportunities):
        """Crée la table des opportunités"""
        if not opportunities:
            return html.Div("Aucune opportunité trouvée", 
                          style={'color': '#e74c3c', 'fontStyle': 'italic'})
        
        # Préparer les données
        data = []
        for opp in opportunities:
            data.append({
                'Paire': opp.symbol,
                'Funding Ext': f"{opp.extended_rate:.6f}",
                'Funding Var': f"{opp.variational_rate:.6f}",
                'Long/Short': f"{opp.long_exchange}/{opp.short_exchange}",
                'Profit 8h': f"${opp.estimated_profit_full_cycle:.4f}",
                '$/heure': f"${opp.profit_per_hour:.4f}",
                'Stratégie': opp.recommended_strategy,
                'Risque': opp.risk_level
            })
        
        return dash_table.DataTable(
            data=data,
            columns=[{"name": i, "id": i} for i in data[0].keys()],
            style_cell={'textAlign': 'left', 'padding': '10px'},
            style_header={
                'backgroundColor': '#3498db',
                'fontWeight': 'bold',
                'color': 'white'
            },
            style_data_conditional=[
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#ecf0f1'
                }
            ]
        )
    
    def create_positions_table(self):
        """Crée la table des positions actives"""
        active_pairs = self.executor.get_active_pairs()
        
        if not active_pairs:
            return html.Div("Aucune position active", 
                          style={'color': '#95a5a6', 'fontStyle': 'italic'})
        
        data = []
        for pair_id, pair in active_pairs.items():
            data.append({
                'ID': pair_id,
                'Paire': pair.symbol,
                'Long': f"{pair.long_position.exchange} @ ${pair.long_position.entry_price:.2f}",
                'Short': f"{pair.short_position.exchange} @ ${pair.short_position.entry_price:.2f}",
                'Funding': f"${pair.total_funding:.4f}",
                'PnL Net': f"${pair.net_pnl:.4f}",
                'Ouvert': pair.opened_at.strftime('%H:%M:%S')
            })
        
        return dash_table.DataTable(
            data=data,
            columns=[{"name": i, "id": i} for i in data[0].keys()],
            style_cell={'textAlign': 'left', 'padding': '10px'},
            style_header={
                'backgroundColor': '#27ae60',
                'fontWeight': 'bold',
                'color': 'white'
            }
        )
    
    def create_balances_info(self):
        """Crée l'affichage des balances"""
        check = self.rebalancer.check_balance_needed()
        
        if not check:
            return html.Div("Impossible de récupérer les balances", 
                          style={'color': '#e74c3c'})
        
        balances = check['balances']
        
        return html.Div([
            html.Div([
                html.Span("Extended: ", style={'fontWeight': 'bold'}),
                html.Span(f"${balances['extended']:,.2f}")
            ]),
            html.Div([
                html.Span("Variational: ", style={'fontWeight': 'bold'}),
                html.Span(f"${balances['variational']:,.2f}")
            ]),
            html.Div([
                html.Span("Total: ", style={'fontWeight': 'bold'}),
                html.Span(f"${balances['total']:,.2f}", 
                         style={'fontSize': '1.2em', 'color': '#2c3e50'})
            ]),
            html.Br(),
            html.Div([
                html.Span("✅ Balances équilibrées" if not check['needs_rebalancing']
                         else "⚠️ Rebalancing recommandé",
                         style={'color': '#27ae60' if not check['needs_rebalancing'] 
                               else '#e67e22'})
            ])
        ], style={'padding': '15px', 'backgroundColor': '#ecf0f1', 'borderRadius': '5px'})
    
    def create_funding_chart(self, funding_data):
        """Crée le graphique des funding rates"""
        traces = []
        
        for symbol, rates in funding_data.items():
            if rates['extended'] and rates['variational']:
                traces.append(go.Bar(
                    name=f"{symbol} - Extended",
                    x=[symbol],
                    y=[rates['extended'].rate],
                    marker_color='#3498db'
                ))
                traces.append(go.Bar(
                    name=f"{symbol} - Variational",
                    x=[symbol],
                    y=[rates['variational'].rate],
                    marker_color='#e74c3c'
                ))
        
        layout = go.Layout(
            title="Comparaison des Funding Rates",
            yaxis={'title': 'Funding Rate'},
            barmode='group',
            plot_bgcolor='#ecf0f1'
        )
        
        return {'data': traces, 'layout': layout}
    
    def run(self, port=None):
        """Lance le dashboard"""
        if port is None:
            port = self.config.get('monitoring', 'dashboard_port', default=8050)
        
        print(f"\n🌐 Dashboard running at http://localhost:{port}")
        print("Press Ctrl+C to stop\n")
        
        self.app.run_server(debug=False, port=port)


def main():
    """Point d'entrée"""
    dashboard = ArbitrageDashboard()
    dashboard.run()


if __name__ == "__main__":
    main()
