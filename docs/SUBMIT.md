# CompliantTender - 提交文案

类别：Intelligent Contracts（0-500 积分）

## 标题

```
CompliantTender - the model filters proposals, the contract picks the winner
```

## 描述

```
Choosing a winning bid is not a fact, so no consensus rule can settle it: two reviewers can both be reasonable and disagree, and a losing bidder can never be shown why it lost. Meeting a written requirement is closer to a fact.

CompliantTender splits the two. The client locks a budget and publishes requirements in prose. Anyone bids a fixed price and a proposal URL. After the window, validators mark each proposal compliant or not, and the contract awards to the cheapest compliant bid - deterministic and replayable. The model cannot pick a winner, change a price, or create a bid.

If nothing complies, the whole budget returns to the client and the tender ends NO_AWARD; rejections are recorded with their reason, so a bidder can read the exact ground for rejection. award() is permissionless, so the client cannot withhold payment by refusing to call it, and cancel() works only before any bid exists.

26 offline tests.
```

## 证明材料

```
https://github.com/IanCao/compliant-tender
https://github.com/IanCao/compliant-tender/blob/main/contracts/compliant_tender.py
https://github.com/IanCao/compliant-tender/blob/main/README.md
https://explorer-studio.genlayer.com/address/0x50Bb3bfd3bD40a9C47205fe92A6Ad28D229B0995
```

第一条是机器校验 `github-repo` 用的仓库根，全新仓库。第四条是本周 Intelligent
Contracts 强制要求的 `genlayer-explorer-contract` 证据。

## 部署（已完成）

Studio → Studionet → 粘贴 `contracts/compliant_tender.py`，无构造参数。
开标：`open_tender("需求文本", 604800)`，附带 value = 预算。

| 项 | 值 |
|---|---|
| 地址 | `0x50Bb3bfd3bD40a9C47205fe92A6Ad28D229B0995` |
| 构造参数 | 无 |
| 链上校验 | schema 含 `open_tender`、`submit_bid`、`award`、`cancel`、`is_bidding_open`；源码 18,852 字符与仓库文件逐字节一致 |

## 自检

- 不是薄 LLM 包装：模型只回答每个投标「是否满足书面要求」，中标与金额由代码决定
- 有可验证行为：26 个离线测试，含更便宜但不合规的投标、并列、全员不合规、四种评审失败
- 与模板有实质区别：核心是「把不可验证的选择权从模型手里拿走」
