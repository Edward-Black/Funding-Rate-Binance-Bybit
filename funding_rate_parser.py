#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Парсер данных Funding Rate в реальном времени с бирж Binance и Bybit
Получает: Funding rate, Time to next funding, Funding interval
"""

import requests
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import json


class FundingRateParser:
    """Парсер funding rate для Binance и Bybit"""
    
    # API endpoints
    BINANCE_BASE_URL = "https://fapi.binance.com"
    BYBIT_BASE_URL = "https://api.bybit.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'FundingRateParser/1.0'
        })
    
    def get_binance_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Получает funding rate с Binance
        
        Args:
            symbol: Торговая пара (например, BTCUSDT)
            
        Returns:
            Dict с данными funding rate или None при ошибке
        """
        try:
            # Получаем текущий funding rate и mark price
            url = f"{self.BINANCE_BASE_URL}/fapi/v1/premiumIndex"
            params = {"symbol": symbol}
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Получаем информацию о funding interval
            url_info = f"{self.BINANCE_BASE_URL}/fapi/v1/fundingInfo"
            params_info = {"symbol": symbol}
            response_info = self.session.get(url_info, params=params_info, timeout=10)
            response_info.raise_for_status()
            info_data = response_info.json()
            
            if not data or not info_data:
                return None
            
            # Binance funding происходит каждые 8 часов (00:00, 08:00, 16:00 UTC)
            funding_interval_hours = 8
            funding_interval_minutes = funding_interval_hours * 60
            
            # Вычисляем время до следующего funding
            now = datetime.utcnow()
            current_hour = now.hour
            current_minute = now.minute
            
            # Находим следующий funding time (00:00, 08:00, 16:00 UTC)
            funding_times = [0, 8, 16]
            next_funding_hour = None
            
            for ft in sorted(funding_times):
                if current_hour < ft or (current_hour == ft and current_minute == 0):
                    next_funding_hour = ft
                    break
            
            if next_funding_hour is None:
                # Следующий funding завтра в 00:00
                next_funding = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            else:
                next_funding = now.replace(hour=next_funding_hour, minute=0, second=0, microsecond=0)
                if next_funding <= now:
                    next_funding += timedelta(hours=8)
            
            time_to_next = next_funding - now
            time_to_next_seconds = int(time_to_next.total_seconds())
            
            return {
                "exchange": "Binance",
                "symbol": symbol,
                "funding_rate": float(data.get("lastFundingRate", 0)),
                "funding_rate_percent": float(data.get("lastFundingRate", 0)) * 100,
                "time_to_next_funding_seconds": time_to_next_seconds,
                "time_to_next_funding_formatted": self._format_time_delta(time_to_next),
                "next_funding_time": next_funding.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "funding_interval_hours": funding_interval_hours,
                "funding_interval_minutes": funding_interval_minutes,
                "mark_price": float(data.get("markPrice", 0)),
                "index_price": float(data.get("indexPrice", 0)),
            }
            
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе к Binance API: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            print(f"Ошибка при обработке данных Binance: {e}")
            return None
    
    def get_bybit_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Получает funding rate с Bybit
        
        Args:
            symbol: Торговая пара (например, BTCUSDT)
            
        Returns:
            Dict с данными funding rate или None при ошибке
        """
        try:
            # Получаем текущий funding rate через ticker
            url = f"{self.BYBIT_BASE_URL}/v5/market/ticker"
            params = {
                "category": "linear",
                "symbol": symbol
            }
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            ticker_data = response.json()
            
            if ticker_data.get("retCode") != 0:
                print(f"Ошибка Bybit API: {ticker_data.get('retMsg')}")
                return None
            
            result = ticker_data.get("result", {})
            if not result or "list" not in result or not result["list"]:
                return None
            
            ticker = result["list"][0]
            
            # Получаем информацию об инструменте для funding interval
            url_info = f"{self.BYBIT_BASE_URL}/v5/market/instruments-info"
            params_info = {
                "category": "linear",
                "symbol": symbol
            }
            response_info = self.session.get(url_info, params=params_info, timeout=10)
            response_info.raise_for_status()
            info_data = response_info.json()
            
            if info_data.get("retCode") != 0:
                print(f"Ошибка Bybit API (instruments-info): {info_data.get('retMsg')}")
                return None
            
            info_result = info_data.get("result", {})
            if not info_result or "list" not in info_result or not info_result["list"]:
                return None
            
            instrument = info_result["list"][0]
            funding_interval_minutes = int(instrument.get("fundingInterval", 480))  # По умолчанию 480 минут (8 часов)
            funding_interval_hours = funding_interval_minutes / 60
            
            # Получаем текущий funding rate
            # Bybit может возвращать fundingRate или predictedFundingRate
            funding_rate = float(ticker.get("fundingRate") or ticker.get("predictedFundingRate", 0))
            
            # Получаем время следующего funding
            next_funding_time_str = ticker.get("nextFundingTime", "") or ticker.get("nextFundingTimeMs", "")
            if next_funding_time_str:
                # Bybit возвращает timestamp в миллисекундах
                next_funding_timestamp = int(next_funding_time_str) / 1000
                next_funding = datetime.utcfromtimestamp(next_funding_timestamp)
                time_to_next = next_funding - datetime.utcnow()
                time_to_next_seconds = max(0, int(time_to_next.total_seconds()))
            else:
                # Если нет данных, вычисляем приблизительно
                now = datetime.utcnow()
                # Bybit funding каждые 8 часов (00:00, 08:00, 16:00 UTC)
                current_hour = now.hour
                funding_times = [0, 8, 16]
                next_funding_hour = None
                
                for ft in sorted(funding_times):
                    if current_hour < ft:
                        next_funding_hour = ft
                        break
                
                if next_funding_hour is None:
                    next_funding = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                else:
                    next_funding = now.replace(hour=next_funding_hour, minute=0, second=0, microsecond=0)
                
                time_to_next = next_funding - now
                time_to_next_seconds = max(0, int(time_to_next.total_seconds()))
            
            return {
                "exchange": "Bybit",
                "symbol": symbol,
                "funding_rate": funding_rate,
                "funding_rate_percent": funding_rate * 100,
                "time_to_next_funding_seconds": time_to_next_seconds,
                "time_to_next_funding_formatted": self._format_time_delta(timedelta(seconds=time_to_next_seconds)),
                "next_funding_time": next_funding.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "funding_interval_hours": funding_interval_hours,
                "funding_interval_minutes": funding_interval_minutes,
                "mark_price": float(ticker.get("markPrice", 0)),
                "index_price": float(ticker.get("indexPrice", 0)),
            }
            
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе к Bybit API: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            print(f"Ошибка при обработке данных Bybit: {e}")
            return None
    
    def _format_time_delta(self, delta: timedelta) -> str:
        """Форматирует timedelta в читаемый формат"""
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}ч {minutes}м {seconds}с"
        elif minutes > 0:
            return f"{minutes}м {seconds}с"
        else:
            return f"{seconds}с"
    
    def get_funding_rates(self, symbol: str) -> Dict:
        """
        Получает funding rate с обеих бирж
        
        Args:
            symbol: Торговая пара (например, BTCUSDT)
            
        Returns:
            Dict с данными от обеих бирж
        """
        results = {
            "symbol": symbol,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "binance": None,
            "bybit": None
        }
        
        print(f"\n{'='*60}")
        print(f"Получение данных для {symbol}...")
        print(f"{'='*60}\n")
        
        # Получаем данные с Binance
        print("Запрос к Binance...", end=" ", flush=True)
        results["binance"] = self.get_binance_funding_rate(symbol)
        if results["binance"]:
            print("✓")
        else:
            print("✗")
        
        # Получаем данные с Bybit
        print("Запрос к Bybit...", end=" ", flush=True)
        results["bybit"] = self.get_bybit_funding_rate(symbol)
        if results["bybit"]:
            print("✓")
        else:
            print("✗")
        
        return results
    
    def display_results(self, results: Dict):
        """Выводит результаты в консоль"""
        symbol = results["symbol"]
        timestamp = results["timestamp"]
        
        print(f"\n{'='*80}")
        print(f"FUNDING RATE DATA - {symbol}")
        print(f"Время запроса: {timestamp}")
        print(f"{'='*80}\n")
        
        # Binance данные
        if results["binance"]:
            binance_data = results["binance"]
            print("📊 BINANCE")
            print(f"  Funding Rate:        {binance_data['funding_rate_percent']:.6f}%")
            print(f"  Time to Next:        {binance_data['time_to_next_funding_formatted']}")
            print(f"  Next Funding Time:   {binance_data['next_funding_time']}")
            print(f"  Funding Interval:    {binance_data['funding_interval_hours']} часов ({binance_data['funding_interval_minutes']} минут)")
            print(f"  Mark Price:          ${binance_data['mark_price']:,.2f}")
            print(f"  Index Price:         ${binance_data['index_price']:,.2f}")
        else:
            print("📊 BINANCE: ❌ Данные не получены")
        
        print()
        
        # Bybit данные
        if results["bybit"]:
            bybit_data = results["bybit"]
            print("📊 BYBIT")
            print(f"  Funding Rate:        {bybit_data['funding_rate_percent']:.6f}%")
            print(f"  Time to Next:        {bybit_data['time_to_next_funding_formatted']}")
            print(f"  Next Funding Time:   {bybit_data['next_funding_time']}")
            print(f"  Funding Interval:    {bybit_data['funding_interval_hours']} часов ({bybit_data['funding_interval_minutes']} минут)")
            print(f"  Mark Price:          ${bybit_data['mark_price']:,.2f}")
            print(f"  Index Price:         ${bybit_data['index_price']:,.2f}")
        else:
            print("📊 BYBIT: ❌ Данные не получены")
        
        print(f"\n{'='*80}\n")
        
        # Сравнение
        if results["binance"] and results["bybit"]:
            binance_data = results["binance"]
            bybit_data = results["bybit"]
            
            diff = bybit_data['funding_rate_percent'] - binance_data['funding_rate_percent']
            print("📈 СРАВНЕНИЕ:")
            print(f"  Разница в Funding Rate: {diff:+.6f}% (Bybit - Binance)")
            if abs(diff) > 0.01:
                if diff > 0:
                    print(f"  ⚠️  Bybit выше на {abs(diff):.6f}%")
                else:
                    print(f"  ⚠️  Binance выше на {abs(diff):.6f}%")
            print()


def main():
    """Основная функция"""
    parser = FundingRateParser()
    
    print("\n" + "="*80)
    print("ПАРСЕР FUNDING RATE - BINANCE & BYBIT")
    print("="*80)
    print("\nВведите торговую пару (например: BTCUSDT, ETHUSDT)")
    print("Или 'exit' для выхода\n")
    
    while True:
        symbol = input("Торговая пара: ").strip().upper()
        
        if symbol.lower() == 'exit':
            print("\nВыход из программы...")
            break
        
        if not symbol:
            print("❌ Пожалуйста, введите торговую пару")
            continue
        
        # Добавляем USDT если не указан
        if not symbol.endswith('USDT'):
            symbol = symbol + 'USDT'
        
        # Получаем данные
        results = parser.get_funding_rates(symbol)
        
        # Выводим результаты
        parser.display_results(results)
        
        # Спрашиваем о режиме реального времени
        print("Выберите режим:")
        print("1. Обновлять автоматически каждые 30 секунд")
        print("2. Однократный запрос (вернуться к выбору пары)")
        print("3. Выход")
        
        choice = input("\nВаш выбор (1/2/3): ").strip()
        
        if choice == '1':
            print("\n🔄 Режим реального времени (Ctrl+C для остановки)\n")
            try:
                while True:
                    time.sleep(30)
                    results = parser.get_funding_rates(symbol)
                    parser.display_results(results)
            except KeyboardInterrupt:
                print("\n\nОстановка обновлений...\n")
                continue
        elif choice == '3':
            print("\nВыход из программы...")
            break
        else:
            continue


if __name__ == "__main__":
    main()
