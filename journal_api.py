"""
API endpoints for Trading Journal - Connected to Agent Trades
Fetches real agent trades instead of separate journal database
"""

from flask import jsonify, request
from datetime import datetime, timedelta


def register_journal_routes(app):
    """Register journal routes that fetch from agent trades"""
    
    # Import app module to get current state of variables
    import app as app_module
    
    @app.route("/api/journal/trades", methods=["GET"])
    def get_all_trades():
        """Get all agent trades with optional filters"""
        try:
            start_date = request.args.get("start_date")
            end_date = request.args.get("end_date")
            symbol = request.args.get("symbol")
            
            # Fetch from agent journal (MongoDB or in-memory)
            if app_module.MONGO_OK:
                query = {}
                if start_date and end_date:
                    query["exit_time"] = {"$gte": start_date, "$lte": end_date + "T23:59:59"}
                elif start_date:
                    query["exit_time"] = {"$gte": start_date}
                    
                if symbol:
                    query["symbol"] = symbol
                
                trades = list(app_module.agent_journal_col.find(query, {"_id": 0}).sort("exit_time", -1).limit(500))
            else:
                # In-memory storage - get current reference
                trades = app_module._ag_mem_journal.copy()
                
                print(f"[JOURNAL API] Total trades in memory: {len(trades)}")
                print(f"[JOURNAL API] Filtering - start_date: {start_date}, end_date: {end_date}")
                
                # Apply filters
                if start_date:
                    trades = [t for t in trades if t.get("exit_time", "").split("T")[0] >= start_date]
                    print(f"[JOURNAL API] After start_date filter: {len(trades)} trades")
                if end_date:
                    trades = [t for t in trades if t.get("exit_time", "").split("T")[0] <= end_date]
                    print(f"[JOURNAL API] After end_date filter: {len(trades)} trades")
                if symbol:
                    trades = [t for t in trades if t.get("symbol") == symbol]
                
                # Debug: print trade details
                for t in trades:
                    print(f"[JOURNAL API] Trade: {t.get('symbol')} exit_time={t.get('exit_time')} p_l={t.get('p_l')}")
                
                # Sort by exit time descending
                trades = sorted(trades, key=lambda x: x.get("exit_time", ""), reverse=True)[:500]
            
            # Convert agent trade format to journal format
            journal_trades = []
            for trade in trades:
                journal_trade = {
                    "id": trade.get("trade_id", ""),
                    "date": trade.get("exit_time", "").split("T")[0] if trade.get("exit_time") else "",
                    "timestamp": trade.get("exit_time", ""),
                    "symbol": trade.get("symbol", ""),
                    "name": trade.get("name", trade.get("symbol", "")),
                    "type": "LONG" if trade.get("side") == "BUY" else "SHORT",
                    "entry_price": trade.get("entry_price", 0),
                    "exit_price": trade.get("exit_price", 0),
                    "quantity": trade.get("quantity", 1),
                    "entry_time": trade.get("entry_time", ""),
                    "exit_time": trade.get("exit_time", ""),
                    "pnl": trade.get("p_l", 0),
                    "pnl_pct": trade.get("p_l_pct", 0),
                    "net_pnl": trade.get("p_l", 0),
                    "fees": 0,
                    "strategy": "AI Agent v3",
                    "setup": trade.get("reason", ""),
                    "notes": f"RSI: {trade.get('rsi', 'N/A')} | Score: {trade.get('score', 'N/A')}/10",
                    "tags": ["agent", "automated"],
                    "ai_signal": trade.get("side", ""),
                    "stop_loss": trade.get("sl", 0),
                    "target": trade.get("target", 0),
                    "sector": trade.get("sector", ""),
                    "status": trade.get("status", "CLOSED")
                }
                journal_trades.append(journal_trade)
            
            return jsonify({
                "success": True,
                "count": len(journal_trades),
                "trades": journal_trades
            })
        except Exception as e:
            print(f"[JOURNAL API] Error fetching trades: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
    
    @app.route("/api/journal/stats", methods=["GET"])
    def get_journal_stats():
        """Get performance statistics from agent trades"""
        try:
            import app as app_module
            days = int(request.args.get("days", 30))
            
            # Calculate cutoff date
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            # Fetch trades from agent journal
            if app_module.MONGO_OK:
                trades = list(app_module.agent_journal_col.find(
                    {"exit_time": {"$gte": cutoff_date}},
                    {"_id": 0}
                ))
            else:
                trades = [t for t in app_module._ag_mem_journal 
                         if t.get("exit_time", "").split("T")[0] >= cutoff_date]
            
            if not trades:
                return jsonify({
                    "success": True,
                    "stats": {
                        "period_days": days,
                        "total_trades": 0,
                        "winning_trades": 0,
                        "losing_trades": 0,
                        "win_rate": 0,
                        "total_pnl": 0,
                        "total_wins": 0,
                        "total_losses": 0,
                        "avg_win": 0,
                        "avg_loss": 0,
                        "largest_win": 0,
                        "largest_loss": 0,
                        "profit_factor": 0
                    }
                })
            
            # Calculate statistics
            winning_trades = [t for t in trades if t.get("p_l", 0) > 0]
            losing_trades = [t for t in trades if t.get("p_l", 0) < 0]
            
            total_pnl = sum(t.get("p_l", 0) for t in trades)
            total_wins = sum(t.get("p_l", 0) for t in winning_trades)
            total_losses = sum(t.get("p_l", 0) for t in losing_trades)
            
            stats = {
                "period_days": days,
                "total_trades": len(trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate": round(len(winning_trades) / len(trades) * 100, 2) if trades else 0,
                "total_pnl": round(total_pnl, 2),
                "total_wins": round(total_wins, 2),
                "total_losses": round(total_losses, 2),
                "avg_win": round(total_wins / len(winning_trades), 2) if winning_trades else 0,
                "avg_loss": round(total_losses / len(losing_trades), 2) if losing_trades else 0,
                "largest_win": round(max((t.get("p_l", 0) for t in trades), default=0), 2),
                "largest_loss": round(min((t.get("p_l", 0) for t in trades), default=0), 2),
                "profit_factor": round(abs(total_wins / total_losses), 2) if total_losses != 0 else 0
            }
            
            return jsonify({
                "success": True,
                "stats": stats
            })
        except Exception as e:
            print(f"[JOURNAL API] Error calculating stats: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
    
    @app.route("/api/journal/export", methods=["GET"])
    def export_journal():
        """Export agent trades to CSV"""
        try:
            import csv
            import os
            import app as app_module
            
            # Fetch all agent trades
            if app_module.MONGO_OK:
                trades = list(app_module.agent_journal_col.find({}, {"_id": 0}).sort("exit_time", -1))
            else:
                trades = sorted(app_module._ag_mem_journal.copy(), 
                              key=lambda x: x.get("exit_time", ""), 
                              reverse=True)
            
            if not trades:
                return jsonify({
                    "success": False,
                    "error": "No trades to export"
                }), 400
            
            # Create export directory
            export_dir = "journal"
            os.makedirs(export_dir, exist_ok=True)
            
            filename = f"agent_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join(export_dir, filename)
            
            # Write CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['date', 'symbol', 'side', 'entry_price', 'exit_price', 
                            'quantity', 'p_l', 'p_l_pct', 'rsi', 'score', 'reason', 'status']
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                
                for trade in trades:
                    row = {
                        'date': trade.get('exit_time', '').split('T')[0],
                        'symbol': trade.get('symbol', ''),
                        'side': trade.get('side', ''),
                        'entry_price': trade.get('entry_price', 0),
                        'exit_price': trade.get('exit_price', 0),
                        'quantity': trade.get('quantity', 1),
                        'p_l': trade.get('p_l', 0),
                        'p_l_pct': trade.get('p_l_pct', 0),
                        'rsi': trade.get('rsi', ''),
                        'score': trade.get('score', ''),
                        'reason': trade.get('reason', ''),
                        'status': trade.get('status', '')
                    }
                    writer.writerow(row)
            
            print(f"[JOURNAL API] Exported {len(trades)} trades to {filepath}")
            return jsonify({
                "success": True,
                "filepath": filepath,
                "message": f"Exported {len(trades)} trades"
            })
        except Exception as e:
            print(f"[JOURNAL API] Export error: {e}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500
    
    print("[API] Journal routes registered (connected to agent trades)")
