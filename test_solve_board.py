"""验证 solve_board 返回值方向"""
from endplay import Deal
from endplay.dds import solve_board
from endplay.types import Denom, Player

# ============================================================
# 残局：每人剩2张♠，共8张牌=2墩，将牌NT
# N=♠AK  E=♠QJ  S=♠32  W=♠54
# 分析：N有最大的♠A和♠K，NS方必定赢2墩
# ============================================================

# === 测试A: N领出(无人出牌), curplayer=N(北/NS方) ===
deal_a = Deal("N:AK... QJ... 32... 54...")
deal_a.trump = Denom.nt
deal_a.first = Player.north
res_a = solve_board(deal_a)
print("=== 测试A: N领出, curplayer=N(NS方) ===")
for c, t in res_a:
    print(f"  {c}: {t} tricks")

# === 测试B: 从完整牌开始，N出♠A, E出♠Q, S出♠3 ===
# 完成后curplayer自动变成W(西/EW方)
deal_b = Deal("N:AK... QJ... 32... 54...")
deal_b.trump = Denom.nt
deal_b.first = Player.north
deal_b.play("♠A", from_hand=True)  # N出♠A, curplayer → E
deal_b.play("♠Q", from_hand=True)  # E出♠Q, curplayer → S
deal_b.play("♠3", from_hand=True)  # S出♠3, curplayer → W
print(f"\n=== 测试B: curplayer={deal_b.curplayer}(EW方) ===")
print(f"  deal.first={deal_b.first}")
res_b = solve_board(deal_b)
for c, t in res_b:
    print(f"  {c}: {t} tricks")

print("\n" + "=" * 70)
print("逻辑分析:")
print("  NS还剩♠K必胜最后1墩 → NS方还能赢 1 墩, EW方赢 0 墩")
print()
print("如果 solve_board 始终返回 NS 方赢墩:")
print("  测试B中W的♠5和♠4都应该显示 1 (NS还剩♠K必胜)")
print()
print("如果 solve_board 返回 curplayer(即W/EW方)所在方的赢墩:")
print("  测试B中W的♠5和♠4都应该显示 0 (EW方赢不了)")
print("=" * 70)
