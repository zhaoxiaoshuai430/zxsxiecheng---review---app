# -*- coding: utf-8 -*-
"""
🏨 酒店运营一体化系统
功能：携程/美团评分预测 + 评论维度分析 + 智能评论回复
"""

import streamlit as st
import pandas as pd
import numpy as np
import math
import re
import matplotlib.pyplot as plt
from collections import defaultdict
from io import BytesIO
import base64
import jieba

# ==================== 页面配置 ====================
st.set_page_config(page_title="Hotel OTA", layout="wide")

# ==================== 初始化 session_state ====================
if 'history' not in st.session_state:
    st.session_state.history = []

if 'hotel_name' not in st.session_state:
    st.session_state.hotel_name = "中油花园酒店"
if 'hotel_nickname' not in st.session_state:
    st.session_state.hotel_nickname = "小油"

# ==================== 工具函数：Excel 导出 ====================
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='原始数据')
    return output.getvalue()

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
    """文本预处理：去除非中文/英文字符，分词"""
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', str(text).lower())
    words = jieba.lcut(text)
    return [w for w in words if len(w) >= 2]

def get_sentiment_score(text):
    """基于关键词的情感分析"""
    words = preprocess(text)
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos_count + neg_count
    if total == 0:
        return 3.8  # 默认中性分
    if pos_count > neg_count:
        return min(5.0, 4.5 + 0.5 * (pos_count / total))
    elif neg_count > pos_count:
        return max(1.0, 2.5 - 0.5 * (neg_count / total))
    else:
        return 3.8

def extract_tags_with_scores(comments):
    """从评论中提取标签并计算情感得分"""
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
    "📊 携程评分提升计算器",
    "📊 美团评分提升计算器",
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

# ============ 1. 携程评分计算器（完全保留您提供的逻辑） ============
if page == "📊 携程评分提升计算器":
    st.title("携程酒店评分提升计算器")

    col1, col2, col3 = st.columns(3)
    with col1:
        weighted_current_score = st.number_input("当前加权综合评分", 0.0, 5.0, 4.52, 0.01)
        score_3_years_ago = st.number_input("三年前评分", 0.0, 5.0, 4.70, 0.01)
    with col2:
        reviews_last_3_years = st.number_input("近三年评价数", 0, 10000, 500, 1)
        reviews_before_3_years = st.number_input("三年前评价数", 0, 10000, 300, 1)
    with col3:
        target_score = st.number_input("目标评分", 0.0, 5.0, 4.80, 0.01)

    def calculate_xiecheng():
        effective_old = reviews_before_3_years / 10.0
        total_weight = reviews_last_3_years + effective_old
        inferred_recent_score = (
            (weighted_current_score * total_weight - score_3_years_ago * effective_old)
            / reviews_last_3_years
        )
        if weighted_current_score >= target_score:
            return 0, inferred_recent_score

        numerator = (target_score * total_weight - score_3_years_ago * effective_old) - inferred_recent_score * reviews_last_3_years
        denominator = 5.0 - target_score
        if denominator <= 0:
            raise ValueError("目标评分过高")
        required = math.ceil(numerator / denominator)
        return max(0, required), inferred_recent_score

    try:
        req, inferred = calculate_xiecheng()
        st.success(f"✅ 反推出近三年真实评分为：**{inferred:.3f} 分**")
        if req == 0:
            st.info(f"🎉 当前评分已达到目标 **{target_score:.2f}** 分")
        else:
            st.warning(f"📈 需要至少 **{req}** 条 5 星好评")
    except Exception as e:
        st.error(f"❌ 计算错误：{str(e)}")

# ============ 2. 美团评分计算器（完全保留您提供的逻辑） ============
elif page == "📊 美团评分提升计算器":
    st.title("美团酒店评分提升计算器")

    col1, col2, col3 = st.columns(3)
    with col1:
        weighted_current_score = st.number_input("当前加权综合评分", 0.0, 5.0, 4.52, 0.01)
        score_1_year_ago = st.number_input("一年前评分", 0.0, 5.0, 4.60, 0.01)
    with col2:
        reviews_last_1_year = st.number_input("近一年评价数", 0, 10000, 300, 1)
        reviews_before_1_year = st.number_input("一年前评价数", 0, 10000, 500, 1)
    with col3:
        target_score = st.number_input("目标评分", 0.0, 5.0, 4.80, 0.01)

    def calculate_meituan():
        effective_old = reviews_before_1_year / 10.0
        total_weight = reviews_last_1_year + effective_old
        inferred_recent_score = (
            (weighted_current_score * total_weight - score_1_year_ago * effective_old)
            / reviews_last_1_year
        )
        if weighted_current_score >= target_score:
            return 0, inferred_recent_score

        numerator = (target_score * total_weight - score_1_year_ago * effective_old) - inferred_recent_score * reviews_last_1_year
        denominator = 5.0 - target_score
        if denominator <= 0:
            raise ValueError("目标评分过高")
        required = math.ceil(numerator / denominator)
        return max(0, required), inferred_recent_score

    try:
        req, inferred = calculate_meituan()
        st.success(f"✅ 反推出近一年真实评分为：**{inferred:.3f} 分**")
        if req == 0:
            st.info(f"🎉 当前评分已达标")
        else:
            st.warning(f"📈 需要至少 **{req}** 条 5 星好评")
    except Exception as e:
        st.error(f"❌ 计算错误：{str(e)}")

# ============ 3. 评论维度分析（自动生成分析文本） ============
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

                    # 可视化
                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("📊 柱状图：各维度评分")
                        filtered_scores = {k: v for k, v in all_scores.items() if 4.5 <= v <= 5.0}
                        fig1, ax1 = plt.subplots(figsize=(10, 6))
                        colors = ['green' if v >= 4.78 else 'red' for v in filtered_scores.values()]
                        pd.Series(filtered_scores).plot(kind='bar', ax=ax1, color=colors, alpha=0.8)
                        ax1.set_ylabel("评分（满分5.0）")
                        ax1.set_ylim(4.5, 5.0)
                        ax1.axhline(y=4.78, color='orange', linestyle='--', linewidth=1)
                        ax1.text(0.02, 4.8, '优秀线 4.78', transform=ax1.transData, fontsize=10, color='orange')
                        plt.xticks(rotation=45, ha='right')
                        plt.tight_layout()
                        st.pyplot(fig1)

                    with col2:
                        st.subheader("📋 评分详情（文本列表）")
                        # 将树状图替换为文本列表
                        st.markdown("#### 所有维度评分：")
                        for dimension, score in all_scores.items():
                            color = "🟢" if score >= 4.78 else "🔴"
                            st.markdown(f"{color} **{dimension}**: {score:.2f}")

                    # 优化建议
                    st.subheader("💡 优化建议（可修改）")
                    needs_improvement = all_scores[all_scores < 4.78]
                    if len(needs_improvement) == 0:
                        st.success("🎉 所有维度均 ≥ 4.78，表现优秀！")
                    else:
                        for dim, score in needs_improvement.items():
                            default_suggestion = SUGGESTIONS.get(dim, "请补充优化建议。")
                            st.markdown(f"### 📌 {dim} ({score:.2f})")
                            st.text_area("建议：", value=default_suggestion, height=100, key=f"sug_{dim}")

                    # 导出原始数据
                    excel_data = to_excel(df)
                    b64 = base64.b64encode(excel_data).decode()
                    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="原始评论数据.xlsx">📥 下载原始数据</a>'
                    st.markdown(href, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ 数据处理失败：{str(e)}")
            st.exception(e)
# ============ 4. 智能评论回复 ============
elif page == "💬 智能评论回复":
    st.title("💬 智能评论回复生成器")

    st.markdown("输入客人评论，系统将生成得体的回复。")

    comment = st.text_area("客人评论", height=150, placeholder="请输入客人的真实评论...")

    if st.button("生成回复"):
        if not comment.strip():
            st.warning("请先输入评论内容")
        else:
            with st.spinner("正在生成回复..."):
                time.sleep(1.5)  # 模拟延迟

                lower_comment = comment.lower()
                is_positive = any(word in lower_comment for word in ['好', '棒', '赞', '满意', '不错', '喜欢'])
                is_negative = any(word in lower_comment for word in ['差', '糟', '烂', '坑', '吵', '脏', '贵', '问题'])

                if is_positive and not is_negative:
                    reply = f"亲爱的客人，您好！\n\n非常感谢您对{st.session_state.hotel_name}的认可与好评！看到您对我们的服务/设施感到满意，我们全体工作人员都倍感欣慰。您的满意是我们前进的最大动力！\n\n期待您再次光临，我们将继续为您提供温馨、舒适的入住体验！\n\n祝您生活愉快，万事如意！\n\n{st.session_state.hotel_nickname} 敬上"
                elif is_negative:
                    reply = f"亲爱的客人，您好！\n\n非常抱歉听到您此次的入住体验未能达到您的期望。关于您提到的 [具体问题，如：噪音/卫生/服务等]，我们已第一时间反馈至相关部门进行核查与改进。\n\n您的反馈对我们至关重要，帮助我们不断提升服务质量。我们诚挚地希望能有机会弥补此次的遗憾，期待您再次光临时，能为您带来焕然一新的入住体验。\n\n祝您顺心如意！\n\n{st.session_state.hotel_nickname} 敬上"
                else:
                    reply = f"亲爱的客人，您好！\n\n感谢您选择入住{st.session_state.hotel_name}并分享您的体验。我们已认真阅读您的反馈。\n\n对于您提到的方面，我们会持续关注并努力优化，力求为每一位客人提供更完美的服务。\n\n期待您的再次光临，祝您一切顺利！\n\n{st.session_state.hotel_nickname} 敬上"

                st.subheader("生成的回复：")
                st.markdown(f"<div style='background-color: #f8f9fa; padding: 15px; border-radius: 8px; font-family: sans-serif;'>{reply}</div>", unsafe_allow_html=True)

                st.session_state.history.append({
                    "comment": comment,
                    "reply": reply,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                })

    if st.session_state.history:
        st.markdown("---")
        st.subheader("📝 历史记录")
        for idx, item in enumerate(reversed(st.session_state.history[-5:]), 1):
            with st.expander(f"记录 {idx} - {item['timestamp']}"):
                st.markdown(f"**评论：** {item['comment']}")
                st.markdown(f"**回复：** {item['reply']}")

# ==================== 尾部信息 ====================
st.sidebar.divider()
st.sidebar.caption("© 2025 酒店运营工具")





