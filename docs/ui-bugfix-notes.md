# Android 界面与交互修复说明

本次修复面向老人端与家属端，基于主线 `03351a4`。代码提交为 `b291943`，推送分支为 `codex/ui-bugfix-20261123`。Android、业务后端及联调同学可据此复查受影响流程。

## 修复内容

| 问题与触发方式 | 修复后的行为 | 主要代码 |
| --- | --- | --- |
| 家属首页将未来、过期、隔日或其他星期执行的提醒计入“今日提醒”，并将已过时或已跳过的事项标为“下次提醒” | 复用现有提醒日历计算当天实际执行项，按真实执行时间排序。“稍后提醒”使用延后时间，跳过和完成状态分别展示 | [HomeFeatures.kt](../android/shared/src/main/java/org/example/niannian/feature/family/HomeFeatures.kt)、[FamilyHomeScreen.kt](../android/shared/src/main/java/org/example/niannian/feature/family/FamilyHomeScreen.kt) |
| 切换家庭时断网，恢复连接并刷新后退回原家庭 | 切换时清除原家庭的成员、授权与选择状态，保留用户刚选中的家庭作为恢复读取目标。授权与成员确认弹窗随账号和家庭切换重置 | [CompanionModel.kt](../android/shared/src/main/java/org/example/niannian/feature/family/CompanionModel.kt)、[CompanionScreen.kt](../android/shared/src/main/java/org/example/niannian/feature/family/CompanionScreen.kt) |
| 提醒保存成功后表单保留旧编辑对象，再次保存会携带旧版本并报冲突，也容易重复创建相同提醒 | 服务端确认保存成功后清空名称与内容，退出旧编辑状态。保存失败时保留输入。取消编辑会同时重置提醒类型，页面按当前账号与家庭核对显示范围 | [ReminderPanel.kt](../android/shared/src/main/java/org/example/niannian/feature/reminder/ReminderPanel.kt) |
| 首页缺少安全区处理，快捷提醒输入区缺少键盘避让，设置弹层未处理系统返回键，家属设置的六个入口挤在同一行 | 首页增加安全区，快捷提醒输入区支持滚动与键盘避让，系统返回键关闭当前设置弹层，快捷入口改为两行。输入草稿随账号、家庭或所选长辈切换重置 | [FamilyHomeScreen.kt](../android/shared/src/main/java/org/example/niannian/feature/family/FamilyHomeScreen.kt)、[ElderHomeScreen.kt](../android/shared/src/main/java/org/example/niannian/feature/family/ElderHomeScreen.kt) |

提醒页面同时移除了固定的“Demo / Mock 登录环境”文案，避免个人账号登录时显示错误的环境信息。

## 已执行验证

- 在原主线代码上复现了家庭切换和今日提醒计算问题，对应回归用例修复后通过。
- Android 共享层单元测试 175 项通过，覆盖断网切换家庭、日期与重复规则、延后时间和跳过状态。
- Windows 客户端现有测试 46 项通过。
- 老人端与家属端的 Demo Debug APK 均构建成功。
- Android 共享模块静态检查为零错误、一条既有警告。警告位于照片导入代码，涉及 `android.media.ExifInterface` 的使用。

## 手机界面待点验

本轮已完成代码、单元测试、构建和静态检查。实际手机上的显示与触控效果仍待验证。

1. 在两个人工创建的测试家庭之间切换，切换时断网，再恢复网络并刷新，确认读取的是刚选中的家庭。
2. 为测试长辈准备今天、明天、已过期、隔日和每周提醒，核对首页计数。提交跳过或稍后反馈后，核对状态与下次时间。
3. 编辑提醒并保存，确认表单退出旧编辑状态。模拟保存失败，确认输入仍在。
4. 在小屏和大字体设置下打开家属设置，检查六个入口的文字与点击范围。打开快捷提醒并弹出键盘，确认可以滚动到保存按钮。
5. 打开两端的设置弹层，使用系统返回键，确认弹层关闭后仍留在首页。
