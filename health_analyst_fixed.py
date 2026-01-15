"""
健康分析与趋势报告模块
用于分析溜槽健康状态、磨损趋势和生成可视化报告
版本: v2.2
"""

import os
import re
import numpy as np
import pandas as pd
import matplotlib
# 设置为非交互式后端，避免在无显示器环境下报错
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
from scipy import stats
import json
import logging

try:
    import config_final as config
except ImportError:
    # 如果导入失败，使用默认值
    class DefaultConfig:
        LOG_FILE = "chute_monitor.log"
        NPY_DIR = "anomaly_samples"
        METADATA_DIR = "anomaly_metadata"
    config = DefaultConfig()
    logging.warning("无法导入config_final，使用默认配置")


class HealthAnalyst:
    """健康分析器 - 长期趋势分析和预测性维护"""
    
    def __init__(self, log_path=None, npy_dir=None, metadata_dir=None):
        self.log_path = log_path or config.LOG_FILE
        self.npy_dir = npy_dir or config.NPY_DIR
        self.metadata_dir = metadata_dir or config.METADATA_DIR
        
        # 匹配更通用的日志格式，兼容逗号和点分隔的毫秒
        self.log_pattern = re.compile(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,\.]\d{3} \[(.*?)\] (.*?): (.*)"
        )

    def parse_logs(self):
        """解析日志文件,提取关键事件"""
        events = []
        if not os.path.exists(self.log_path):
            logging.warning(f"日志文件不存在: {self.log_path}")
            return pd.DataFrame()

        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    match = self.log_pattern.search(line)
                    if match:
                        ts_str, level, thread, msg = match.groups()
                        try:
                            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                            
                            # 使用英文和中文关键词匹配
                            if "S2_ACTION" in msg or "触发拍打器" in msg or "PATTING" in msg:
                                events.append({'ts': ts, 'type': 'TRIGGER', 'val': 1})
                            elif "自愈成功" in msg or "RECOVERED" in msg:
                                events.append({'ts': ts, 'type': 'RECOVERED', 'val': 1})
                            elif "紧急停机" in msg or "STOP_BELT" in msg:
                                events.append({'ts': ts, 'type': 'EMERGENCY', 'val': 1})
                            elif "S1_PRE_WARN" in msg or "预警状态" in msg:
                                events.append({'ts': ts, 'type': 'PREWARN', 'val': 1})
                        except ValueError as e:
                            logging.debug(f"解析时间戳失败 (行{line_num}): {e}")
                            continue
        except Exception as e:
            logging.error(f"解析日志文件失败: {e}")
            return pd.DataFrame()
        
        return pd.DataFrame(events)

    def parse_metadata_files(self):
        """解析所有元数据文件，提取详细事件信息"""
        metadata_list = []
        
        if not os.path.exists(self.metadata_dir):
            logging.warning(f"元数据目录不存在: {self.metadata_dir}")
            return pd.DataFrame()
        
        try:
            files = [f for f in os.listdir(self.metadata_dir) if f.endswith('.json')]
            
            for fname in files:
                filepath = os.path.join(self.metadata_dir, fname)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                        # 提取关键字段
                        record = {
                            'filename': fname,
                            'timestamp': data.get('timestamp', ''),
                            'rmse': data.get('rmse', 0),
                            'thresh_a': data.get('thresh_a', 0),
                            'thresh_b': data.get('thresh_b', 0),
                            'state': data.get('state', ''),
                            'retry_count': data.get('retry_count', 0),
                            # [新增] v2.1 新字段
                            'recovery_duration': data.get('recovery_duration', None),
                            'rmse_after_recovery': data.get('rmse_after_recovery', None),
                            'patter_trigger_count': data.get('patter_trigger_count', 0)
                        }
                        metadata_list.append(record)
                except json.JSONDecodeError as e:
                    # [修复v2.2] 记录具体错误而不是静默忽略
                    logging.warning(f"JSON解析失败 {fname}: {e}")
                    continue
                except Exception as e:
                    logging.warning(f"读取元数据文件失败 {fname}: {e}")
                    continue
            
            return pd.DataFrame(metadata_list)
            
        except Exception as e:
            logging.error(f"解析元数据文件失败: {e}")
            return pd.DataFrame()

    def analyze_wear_trend(self):
        """分析磨损趋势"""
        df = self.parse_logs()
        if df.empty: 
            return None, None
        
        try:
            df.set_index('ts', inplace=True)
            daily_triggers = df[df['type'] == 'TRIGGER'].resample('D').count()['val']
            
            y = daily_triggers.values
            if len(y) < 2:
                slope, intercept, r_value = 0.0, 0.0, 0.0
            else:
                x = np.arange(len(y))
                slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            
            # 统计异常样本数量
            anomaly_files = []
            if os.path.exists(self.npy_dir):
                anomaly_files = [f for f in os.listdir(self.npy_dir) if f.endswith('.npy')]
            
            # 计算健康状态
            if slope <= 0.05:
                health_status = "Excellent"
            elif slope < 0.2:
                health_status = "Warning"
            else:
                health_status = "Critical"
            
            # [新增] 分析恢复效率
            metadata_df = self.parse_metadata_files()
            avg_recovery_duration = None
            recovery_success_rate = None
            
            if not metadata_df.empty:
                # 计算平均恢复时间
                recovery_durations = metadata_df['recovery_duration'].dropna()
                if len(recovery_durations) > 0:
                    avg_recovery_duration = float(recovery_durations.mean())
                
                # 计算恢复成功率
                total_triggers = len(metadata_df)
                successful_recoveries = len(metadata_df[
                    metadata_df['rmse_after_recovery'].notna() & 
                    (metadata_df['rmse_after_recovery'] < metadata_df['thresh_a'])
                ])
                if total_triggers > 0:
                    recovery_success_rate = successful_recoveries / total_triggers
            
            report = {
                "analysis_period": f"{len(daily_triggers)} days",
                "total_triggers": int(y.sum()) if len(y) > 0 else 0,
                "wear_slope": round(float(slope), 4),
                "intercept": round(float(intercept), 4),
                "confidence_r2": round(float(r_value**2), 4),
                "anomaly_sample_count": len(anomaly_files),
                "health_status": health_status,
                "avg_daily_triggers": round(float(np.mean(y)), 2) if len(y) > 0 else 0.0,
                "max_daily_triggers": int(np.max(y)) if len(y) > 0 else 0,
                # [新增] v2.1 新指标
                "avg_recovery_duration_sec": avg_recovery_duration,
                "recovery_success_rate": round(recovery_success_rate, 4) if recovery_success_rate else None
            }
            return report, daily_triggers
        except Exception as e:
            logging.error(f"分析趋势失败: {e}", exc_info=True)
            return None, None

    def analyze_recovery_efficiency(self):
        """分析恢复效率趋势 [新增 v2.1]"""
        metadata_df = self.parse_metadata_files()
        if metadata_df.empty:
            return None
        
        try:
            # 按日期分组分析
            metadata_df['date'] = pd.to_datetime(
                metadata_df['timestamp'], 
                format='%Y%m%d_%H%M%S',
                errors='coerce'
            ).dt.date
            
            daily_stats = metadata_df.groupby('date').agg({
                'rmse': ['mean', 'max'],
                'recovery_duration': 'mean',
                'retry_count': 'mean'
            }).reset_index()
            
            daily_stats.columns = ['date', 'avg_rmse', 'max_rmse', 
                                   'avg_recovery_duration', 'avg_retry_count']
            
            return daily_stats
            
        except Exception as e:
            logging.error(f"分析恢复效率失败: {e}", exc_info=True)
            return None

    def generate_visual_report(self, output_path="health_trend_report.png"):
        """生成可视化健康报告"""
        report, daily_data = self.analyze_wear_trend()
        
        if not report:
            print("暂无数据生成报告")
            return None
        
        try:
            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            
            # 子图1: 每日触发次数趋势
            ax1 = axes[0, 0]
            if daily_data is not None and len(daily_data) > 0:
                x = np.arange(len(daily_data))
                ax1.bar(x, daily_data.values, alpha=0.7, color='steelblue', label='Daily Triggers')
                
                # 添加趋势线
                if len(x) > 1:
                    slope = report['wear_slope']
                    intercept = report['intercept']
                    trend_line = slope * x + intercept
                    ax1.plot(x, trend_line, 'r--', linewidth=2, 
                            label=f'Trend (slope={slope:.4f})')
                
                ax1.set_xlabel("Day")
                ax1.set_ylabel("Trigger Count")
                ax1.legend(loc='best', fontsize=8)
            else:
                ax1.text(0.5, 0.5, 'No Data', ha='center', va='center', fontsize=14)
            
            ax1.set_title("Daily Trigger Trend", fontsize=12, fontweight='bold')
            ax1.grid(True, alpha=0.3)
            
            # 子图2: 健康状态仪表盘
            ax2 = axes[0, 1]
            status_color = {
                'Excellent': 'green',
                'Warning': 'orange', 
                'Critical': 'red'
            }
            color = status_color.get(report['health_status'], 'gray')
            
            # 绘制简单的状态指示
            circle = plt.Circle((0.5, 0.5), 0.3, color=color, alpha=0.7)
            ax2.add_patch(circle)
            ax2.text(0.5, 0.5, report['health_status'], ha='center', va='center', 
                    fontsize=16, fontweight='bold', color='white')
            ax2.text(0.5, 0.1, f"R² = {report['confidence_r2']:.4f}", 
                    ha='center', fontsize=10)
            ax2.set_xlim(0, 1)
            ax2.set_ylim(0, 1)
            ax2.set_aspect('equal')
            ax2.axis('off')
            ax2.set_title("Health Status", fontsize=12, fontweight='bold')
            
            # 子图3: 统计摘要
            ax3 = axes[1, 0]
            ax3.axis('off')
            
            summary_text = f"""
            Analysis Summary
            ─────────────────────────────
            Period:          {report['analysis_period']}
            Total Triggers:  {report['total_triggers']}
            Avg Daily:       {report['avg_daily_triggers']}
            Max Daily:       {report['max_daily_triggers']}
            Wear Slope:      {report['wear_slope']}
            Anomaly Samples: {report['anomaly_sample_count']}
            """
            
            if report.get('avg_recovery_duration_sec'):
                summary_text += f"\n            Avg Recovery:    {report['avg_recovery_duration_sec']:.2f}s"
            if report.get('recovery_success_rate'):
                summary_text += f"\n            Recovery Rate:   {report['recovery_success_rate']*100:.1f}%"
            
            ax3.text(0.1, 0.9, summary_text, transform=ax3.transAxes, fontsize=11,
                    verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
            ax3.set_title("Statistics", fontsize=12, fontweight='bold')
            
            # 子图4: 恢复效率趋势
            ax4 = axes[1, 1]
            recovery_stats = self.analyze_recovery_efficiency()
            
            if recovery_stats is not None and not recovery_stats.empty:
                if 'avg_recovery_duration' in recovery_stats.columns:
                    valid_data = recovery_stats.dropna(subset=['avg_recovery_duration'])
                    if len(valid_data) > 0:
                        ax4.bar(range(len(valid_data)), 
                               valid_data['avg_recovery_duration'].values,
                               color='coral', alpha=0.7, label='Avg Recovery Time')
                        ax4.set_xlabel("Day")
                        ax4.set_ylabel("Recovery Duration (s)")
                        ax4.legend(loc='best', fontsize=8)
            
            ax4.set_title("Recovery Efficiency Trend", fontsize=12, fontweight='bold')
            ax4.grid(True, alpha=0.3)
            
            # 总标题
            fig.suptitle(f"Chute Health Analysis Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}", 
                        fontsize=14, fontweight='bold')
            
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            # 打印报告
            print("\n" + "="*50)
            print("           HEALTH ANALYSIS REPORT")
            print("="*50)
            for k, v in report.items(): 
                if v is not None:
                    print(f"{k:30}: {v}")
            print("="*50)
            print(f"Report saved to: {output_path}\n")
            
            return report
            
        except Exception as e:
            logging.error(f"生成可视化报告失败: {e}", exc_info=True)
            return report

    def get_latest_anomalies(self, n=10):
        """获取最近的异常样本信息"""
        if not os.path.exists(self.npy_dir):
            return []
        
        try:
            files = [f for f in os.listdir(self.npy_dir) if f.endswith('.npy')]
            files.sort(reverse=True)  # 按文件名倒序(时间戳)
            
            anomalies = []
            for fname in files[:n]:
                # 解析文件名: err_20240115_120530_0.4567.npy
                parts = fname.replace('.npy', '').split('_')
                if len(parts) >= 4:
                    timestamp = f"{parts[1]}_{parts[2]}"
                    try:
                        rmse = float(parts[3]) if len(parts) > 3 else 0.0
                    except ValueError:
                        rmse = 0.0
                    
                    # 尝试加载元数据
                    metadata_file = os.path.join(self.metadata_dir, 
                                                fname.replace('.npy', '.json'))
                    metadata = {}
                    if os.path.exists(metadata_file):
                        try:
                            with open(metadata_file, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                        except Exception as e:
                            logging.debug(f"读取元数据失败 {metadata_file}: {e}")
                    
                    anomalies.append({
                        'filename': fname,
                        'timestamp': timestamp,
                        'rmse': rmse,
                        'recovery_duration': metadata.get('recovery_duration'),
                        'rmse_after_recovery': metadata.get('rmse_after_recovery'),
                        'metadata': metadata
                    })
            
            return anomalies
        except Exception as e:
            logging.error(f"获取异常样本信息失败: {e}", exc_info=True)
            return []

    def print_summary(self):
        """打印汇总信息"""
        report, _ = self.analyze_wear_trend()
        if not report:
            print("暂无数据可供分析")
            return
        
        print("\n" + "="*60)
        print("                    QUICK SUMMARY")
        print("="*60)
        print(f"健康状态:         {report['health_status']}")
        print(f"分析周期:         {report['analysis_period']}")
        print(f"总触发次数:       {report['total_triggers']}")
        print(f"平均每日触发:     {report['avg_daily_triggers']}")
        print(f"磨损趋势斜率:     {report['wear_slope']}")
        print(f"R² 拟合度:        {report['confidence_r2']}")
        
        if report.get('avg_recovery_duration_sec'):
            print(f"平均恢复时间:     {report['avg_recovery_duration_sec']:.2f}秒")
        if report.get('recovery_success_rate'):
            print(f"恢复成功率:       {report['recovery_success_rate']*100:.1f}%")
        
        print("="*60 + "\n")
        
        # 显示最近异常
        print("最近10次异常事件:")
        anomalies = self.get_latest_anomalies(10)
        if anomalies:
            for i, anom in enumerate(anomalies, 1):
                recovery_info = ""
                if anom.get('recovery_duration'):
                    recovery_info = f" | 恢复耗时: {anom['recovery_duration']:.1f}s"
                print(f"  {i}. {anom['timestamp']} - RMSE: {anom['rmse']:.4f}{recovery_info}")
        else:
            print("  暂无异常记录")
        print()

    def detailed_analysis(self):
        """详细分析（包含更多统计信息）"""
        report, daily_data = self.analyze_wear_trend()
        if not report:
            print("暂无数据可供详细分析")
            return
        
        df = self.parse_logs()
        
        print("\n" + "="*70)
        print("                    DETAILED ANALYSIS")
        print("="*70)
        
        # 基本信息
        print(f"\n【基本信息】")
        print(f"  分析周期:       {report['analysis_period']}")
        print(f"  健康状态:       {report['health_status']}")
        print(f"  异常样本数:     {report['anomaly_sample_count']}")
        
        # 触发统计
        print(f"\n【触发统计】")
        print(f"  总触发次数:     {report['total_triggers']}")
        print(f"  平均每日:       {report['avg_daily_triggers']}")
        print(f"  最大单日:       {report['max_daily_triggers']}")
        
        # 趋势分析
        print(f"\n【趋势分析】")
        print(f"  磨损斜率:       {report['wear_slope']}")
        print(f"  R² 拟合度:      {report['confidence_r2']}")
        print(f"  截距:           {report['intercept']}")
        
        trend_desc = ""
        if report['wear_slope'] > 0.2:
            trend_desc = "严重恶化 - 建议立即维护"
        elif report['wear_slope'] > 0.05:
            trend_desc = "缓慢恶化 - 建议安排预防性维护"
        elif report['wear_slope'] < -0.05:
            trend_desc = "改善中 - 维护效果良好"
        else:
            trend_desc = "稳定 - 保持当前维护策略"
        print(f"  趋势描述:       {trend_desc}")
        
        # [新增] 恢复效率分析
        print(f"\n【恢复效率分析】")
        if report.get('avg_recovery_duration_sec'):
            print(f"  平均恢复时间:   {report['avg_recovery_duration_sec']:.2f}秒")
        else:
            print(f"  平均恢复时间:   暂无数据")
            
        if report.get('recovery_success_rate'):
            print(f"  恢复成功率:     {report['recovery_success_rate']*100:.1f}%")
        else:
            print(f"  恢复成功率:     暂无数据")
        
        # 事件类型统计
        if not df.empty:
            print(f"\n【事件类型统计】")
            event_counts = df.groupby('type')['val'].sum()
            for event_type, count in event_counts.items():
                print(f"  {event_type:12}: {int(count):4} 次")
        
        print("="*70 + "\n")

    def export_to_csv(self, output_path="health_data_export.csv"):
        """导出分析数据到CSV文件"""
        try:
            # 合并日志和元数据
            log_df = self.parse_logs()
            metadata_df = self.parse_metadata_files()
            
            # 保存日志数据
            if not log_df.empty:
                log_output = output_path.replace('.csv', '_logs.csv')
                log_df.to_csv(log_output, index=True)
                print(f"日志数据已导出: {log_output}")
            
            # 保存元数据
            if not metadata_df.empty:
                metadata_output = output_path.replace('.csv', '_metadata.csv')
                metadata_df.to_csv(metadata_output, index=False)
                print(f"元数据已导出: {metadata_output}")
            
            return True
        except Exception as e:
            logging.error(f"导出CSV失败: {e}", exc_info=True)
            return False


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    analyst = HealthAnalyst()
    analyst.print_summary()
    analyst.detailed_analysis()
    analyst.generate_visual_report()
