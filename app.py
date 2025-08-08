# -*- coding: utf-8 -*-
"""
🏨 酒店运营一体化系统
功能：携程/美团评分计算 + 评论维度分析（文本挖掘）+ 智能评论回复
"""

import streamlit as st
import pandas as pd
import numpy as np
import math
import requests
import time
import re
import os
from datetime import datetime
import jieba
from collections import defaultdict
import matplotlib.pyplot as plt
from io import BytesIO
import base64

# ==================== 页面配置 ====================
st.set_page_config(page_title="Hotel OTA", layout="wide")

# ==================== 初始化 session_state ====================
if 'history' not in st.session_state:
    st.session_state.history = []

if 'hotel_name' not in st.session_state:
    st.session_state.hotel_name = "星辰花园酒店"
if 'hotel_nickname' not in st.session_state:
    st.session_state.hotel_nickname = "小油"

# ==================== 工具函数：Excel 导出 ====================
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='原始数据')
    return output.getvalue()

# ==================== 工具函数：加权评分计算 ====================
def calculate_time_and_rank_weighted_score(df, score_col, date_col="入住时间"):
    # （保持不变）
    pass  # 为简洁省略，实际代码中保留

# ==================== 工具函数：情感分析与标签提取 ====================
TAG_KEYWORDS = {
    '位置': ['位置', '地段', '周边', '附近', '离', '靠近', '市中心', '地铁', '公交'],
    '交通': ['交通', '打车', '停车', '驾车', '机场', '车站', '接驳'],
    '早餐': ['早餐', '早饭', '餐饮', 'buffet', '餐食', '自助餐'],
    '安静': ['安静', '噪音', '吵', '吵闹', '隔音', '清静', '安静房'],
    '床舒适': ['床', '床垫', '睡感', '舒服', '舒不舒服', '软硬', '枕头'],
    '房间大小': ['房间小', '房间大', '空间', '拥挤', '宽敞', '面积', '局促'],
    '视野': ['视野', '景观', '江景', '海景', '窗景', '朝向', '夜景', 'view'],
    '性价比': ['性价比', '价格', '划算', '贵', '便宜', '值', '物超所值'],
    '前台': ['前台', '接待', 'check in', '入住办理', '退房', '接待员'],
    '网络': ['Wi-Fi', '网络', '信号', '上网', '网速', 'wifi', '无线']
}

POSITIVE_WORDS = {'好', '棒', '赞', '满意', '不错', '推荐', '惊喜', '舒服', '完美', '贴心',
                  '干净', '方便', '快捷', '温馨', '柔软', '丰富', '齐全', '优质', '热情'}
NEGATIVE_WORDS = {'差', '糟', '烂', '坑', '差劲', '失望', '糟糕', '难用', '吵', '脏',
                  '贵', '偏', '慢', '不值', '问题', '敷衍', '拖延', '恶劣'}

def preprocess(text):
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', str(text).lower())
    words = jieba.lcut(text)
    return [w for w in words if len(w) >= 2]

def get_sentiment_score(text):
    words = preprocess(text)
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos_count + neg_count
    if total == 0:
        return 3.8
    if pos_count > neg_count:
        return min(5.0, 4.5 + 0.5 * (pos_count / total))
    elif neg_count > pos_count:
        return max(1.0, 2.5 - 0.5 * (neg_count / total))
    else:
        return 3.8

def extract_tags_with_scores(comments):
    tag_scores = defaultdict(list)
    for comment in comments.dropna():
        for tag, keywords in TAG_KEYWORDS.items():
            if any(kw in str(comment) for kw in keywords):
                score = get_sentiment_score(str(comment))
                tag_scores[tag].append(score)
    final_scores = {
        tag: round(sum(scores) / len(scores), 2)
        for tag, scores in tag_scores.items()
        if len(scores) > 0
    }
    return final_scores

# ==================== 优化建议库 ====================
SUGGESTIONS = {
    '总评分': '整体体验需提升，建议从服务和设施入手，加强客户反馈闭环管理。',
    '设施评分': '检查老旧设备，制定更新计划，增加智能化设施如智能门锁、语音助手。',
    '服务评分': '加强员工服务意识培训，建立快速响应机制处理差评。',
    '卫生评分': '加强清洁流程监督，引入第三方质检或公示消毒记录增强信任。',
    '位置': '优化导航信息，与周边商圈合作提供折扣弥补位置短板。',
    '交通': '提供免费接驳车或与打车平台合作，提升客人便利性。',
    '早餐': '丰富早餐品类，增加本地特色和健康选项，提升餐品温度。',
    '安静': '优化隔音设计，更换密封性更好的门窗，减少噪音干扰。',
    '床舒适': '升级床垫与床品材质，提供软硬两种枕头供客人选择。',
    '房间大小': '优化小房型空间布局，推出“大房型优先升级”优惠活动。',
    '视野': '定期清洁窗户与阳台，避免景观遮挡，拍摄高质量宣传图。',
    '性价比': '调整价格策略，推出不同时段优惠套餐，增加增值服务。',
    '前台': '缩短入住/退房等待时间，推行自助机或移动端办理。',
    '网络': '升级Wi-Fi带宽，确保全区域稳定覆盖，设置一键连接页面。'
}

# ==================== 侧边栏导航 ====================
st.sidebar.title("🏨 酒店OTA")
page = st.sidebar.radio("选择功能", [
    "📊 携程评分计算器",
    "📊 美团评分计算器",
    "📈 评论维度分析",
    "💬 智能评论回复"
])

# 全局配置
st.sidebar.divider()
st.sidebar.subheader("⚙️ 酒店配置")
hotel_name = st.sidebar.text_input("酒店名称", st.session_state.hotel_name)
hotel_nickname = st.sidebar.text_input("助手昵称", st.session_state.hotel_nickname)
if st.sidebar.button("💾 保存配置"):
    st.session_state.hotel_name = hotel_name.strip() or "未命名酒店"
    st.session_state.hotel_nickname = hotel_nickname.strip() or "助手"
    st.sidebar.success("✅ 配置已保存")

# ==================== 主页面逻辑 ====================

# ... (其他页面代码保持不变)

# ============ 3. 评论维度分析（修改：自动生成连贯文本） ============
elif page == "📈 评论维度分析":
    st.title("📈 评论维度分析（基于文本挖掘）")

    st.markdown("上传包含 **评论内容** 列的 Excel 文件，系统将自动提取标签并分析情感。")

    with st.expander("📄 示例格式"):
        st.write(pd.DataFrame({
            '评论内容': ["位置很好，靠近地铁，但房间有点小。", "早餐丰富，服务热情，就是有点吵。"]
        }))

    uploaded_file = st.file_uploader("上传评论数据 (.xlsx)", type=["xlsx"])

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            st.success(f"✅ 成功加载 {len(df)} 条评论数据")

            with st.expander("📄 数据预览"):
                st.dataframe(df.head())

            # 查找评论列
            comment_col = None
            if '评论内容' in df.columns:
                comment_col = '评论内容'
            else:
                potential = [col for col in df.columns if '评论' in col or '评价' in col or 'content' in col]
                if potential:
                    comment_col = potential[0]

            if not comment_col:
                st.error("❌ 未找到评论列，请确保包含“评论”或“评价”关键词的列。")
            else:
                # 提取标签评分
                new_scores = extract_tags_with_scores(df[comment_col])

                if len(new_scores) == 0:
                    st.warning("⚠️ 未提取到任何有效标签评分")
                else:
                    all_scores = pd.Series(new_scores).sort_values(ascending=False)
                    excellent_line = 4.78

                    # --- 生成柱状图 ---
                    fig1, ax1 = plt.subplots(figsize=(10, 6))
                    colors = ['green' if v >= excellent_line else 'red' for v in all_scores.values]
                    bars = ax1.bar(all_scores.index, all_scores.values, color=colors, alpha=0.8)
                    ax1.axhline(y=excellent_line, color='blue', linestyle='--', linewidth=2, label='优秀线 (4.78)')
                    ax1.set_title('各维度评分', fontsize=16, fontweight='bold')
                    ax1.set_ylabel('评分')
                    ax1.set_ylim(1, 5)
                    ax1.legend()
                    for bar, score in zip(bars, all_scores.values):
                        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                                 f'{score:.2f}', ha='center', va='bottom', fontsize=10)
                    plt.xticks(rotation=45)
                    plt.tight_layout()

                    # --- 生成树状图 ---
                    fig2, ax2 = plt.subplots(figsize=(10, 6))
                    sorted_scores = all_scores.sort_values()
                    y_pos = np.arange(len(sorted_scores))
                    colors2 = ['green' if v >= excellent_line else 'red' for v in sorted_scores.values]
                    bars2 = ax2.barh(y_pos, sorted_scores.values, color=colors2, alpha=0.8)
                    ax2.axvline(x=excellent_line, color='blue', linestyle='--', linewidth=2, label='优秀线 (4.78)')
                    ax2.set_title('各维度评分 (树状图)', fontsize=16, fontweight='bold')
                    ax2.set_xlabel('评分')
                    ax2.set_yticks(y_pos)
                    ax2.set_yticklabels(sorted_scores.index)
                    ax2.legend()
                    for i, (bar, score) in enumerate(zip(bars2, sorted_scores.values)):
                        ax2.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height() / 2,
                                 f'{score:.2f}', va='center', fontsize=10)
                    plt.tight_layout()

                    # --- 展示图表 ---
                    col1, col2 = st.columns(2)
                    with col1:
                        st.pyplot(fig1)
                    with col2:
                        st.pyplot(fig2)

                    # --- 核心修改：自动生成连贯的分析文本 ---
                    st.subheader("📝 分析报告")

                    # 1. 总体评价
                    avg_score = all_scores.mean()
                    if avg_score >= 4.5:
                        overall_status = "整体表现优秀"
                    elif avg_score >= 4.0:
                        overall_status = "整体表现良好，但有提升空间"
                    else:
                        overall_status = "整体表现有待大幅提升"

                    report_parts = [f"根据对 {len(df)} 条客人评论的分析，{st.session_state.hotel_name} 的 {overall_status}。"]

                    # 2. 亮点维度（评分 >= 4.78）
                    strengths = all_scores[all_scores >= excellent_line]
                    if len(strengths) > 0:
                        strength_list = [f"{dim}（{score:.2f}分）" for dim, score in strengths.items()]
                        report_parts.append(f"在以下 {len(strengths)} 个维度表现尤为突出：{', '.join(strength_list)}。")

                    # 3. 待改进维度（评分 < 4.78）
                    weaknesses = all_scores[all_scores < excellent_line]
                    if len(weaknesses) > 0:
                        report_parts.append("需要重点关注并改进的维度包括：")
                        for dim, score in weaknesses.items():
                            suggestion = SUGGESTIONS.get(dim, "建议加强管理。")
                            report_parts.append(f"  • **{dim}**（{score:.2f}分）：{suggestion}")

                    # 4. 生成最终文本
                    auto_text = "\n\n".join(report_parts)
                    st.markdown(auto_text)

                    # --- 结束 ---

                    # 导出原始数据
                    excel_data = to_excel(df)
                    b64 = base64.b64encode(excel_data).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="原始评论数据.xlsx">📥 下载原始数据</a>'
                    st.markdown(href, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ 数据处理失败：{str(e)}")
            st.exception(e)
