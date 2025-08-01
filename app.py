import streamlit as st
import math

def calculate_required_reviews(weighted_current_score, score_3_years_ago, target_score, reviews_last_3_years, reviews_before_3_years):
    """
    根据加权评分和三年前评分，反推近三年真实评分，并计算所需 5 星评论数。
    """
    # 反推近三年真实评分
    current_score_recent = (weighted_current_score - score_3_years_ago * 0.1) / 0.9

    if current_score_recent < 0 or current_score_recent > 5.0:
        raise ValueError("输入的【加权评分】与【三年前评分】组合不合理，反推出的【近三年评分】超出 0~5 范围。")

    # 当前近三年总得分
    current_total_recent_score = current_score_recent * reviews_last_3_years

    # 计算目标所需的“近三年评分”
    required_recent_score = (target_score - score_3_years_ago * 0.1) / 0.9

    if required_recent_score >= 5.0:
        raise ValueError("目标评分过高，即使全为5星也无法达到。")

    # 解方程：(current_total_recent_score + 5*R) / (reviews_last_3_years + R) >= required_recent_score
    N = reviews_last_3_years
    A = current_total_recent_score
    req = required_recent_score

    numerator = req * N - A
    denominator = 5.0 - req

    if numerator <= 0:
        return 0, current_score_recent  # 已达标

    if denominator <= 0:
        raise ValueError("目标评分不合法，导致分母非正。")

    required_5_star = numerator / denominator
    required_5_star = math.ceil(required_5_star)

    return required_5_star, current_score_recent


# ========== Streamlit 界面 ==========
st.title("📊 酒店携程评分提升计算器")
st.markdown("""
- ✅ 输入【当前加权综合评分】与【三年前评分】
- ✅ 自动反推【近三年真实评分】
- ✅ 支持【三年前评论数 10:1 折算】
- ✅ 精准计算所需 5 星好评数量
""")

# 重新布局：左侧（评分）｜ 中间（评论数量）｜ 右侧（目标设置）
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("📌 评分输入")
    weighted_current_score = st.number_input(
        "当前加权综合评分",
        min_value=0.0,
        max_value=5.0,
        value=4.52,
        step=0.01,
        help="即平台展示的最终评分，如 4.52"
    )
    score_3_years_ago = st.number_input(
        "三年前评分",
        min_value=0.0,
        max_value=5.0,
        value=4.70,
        step=0.01,
        help="三年前的好评率，可手动调整"
    )

with col2:
    st.subheader("📝 评论数量")
    reviews_last_3_years = st.number_input(
        "近三年评价数",
        min_value=0,
        value=500,
        step=1
    )
    reviews_before_3_years = st.number_input(
        "三年前评价数",
        min_value=0,
        value=300,
        step=1
    )

with col3:
    st.subheader("🎯 目标设置")
    target_score = st.number_input(
        "目标评分",
        min_value=0.0,
        max_value=5.0,
        value=4.80,
        step=0.01
    )

# === 计算与结果 ===
try:
    required_5_star, inferred_recent_score = calculate_required_reviews(
        weighted_current_score, score_3_years_ago, target_score, reviews_last_3_years, reviews_before_3_years
    )

    st.success(f"✅ 反推出近三年真实评分为：**{inferred_recent_score:.3f} 分**")

    if required_5_star == 0:
        st.info(f"🎉 当前评分已达到或超过目标 **{target_score:.2f}** 分，无需新增好评！")
    else:
        st.warning(f"📈 要达到 **{target_score:.2f}** 分，还需要至少 **{required_5_star}** 条 5 星好评")

    # 展开查看详情
    with st.expander("🔍 查看详细计算过程"):
        effective_old = reviews_before_3_years / 10.0
        st.write(f"""
        - 当前加权评分：{weighted_current_score:.2f}
        - 三年前评分：{score_3_years_ago:.2f}
        - 反推近三年评分：{inferred_recent_score:.3f}
        - 近三年评价数：{reviews_last_3_years}
        - 三年前评价数：{reviews_before_3_years}（按 10:1 折算 → 等效 {effective_old:.1f} 条）
        - 目标评分：{target_score:.2f}
        - 需新增 5 星评论：{required_5_star} 条
        """)

except ValueError as e:
    st.error(f"❌ 计算错误：{str(e)}")

# 保持运行
if __name__ == "__main__":
    pass