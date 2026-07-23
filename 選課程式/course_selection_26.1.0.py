import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ================= 選課設定區 =================
select_TIME = "2026-06-06 1:42:20"

# 課程代碼清單
TARGET_COURSES_TEXT = """
I4820
I5420
E4270
E4800
E4250
I4390
"""

my_studentID = "411206233"
my_password = "Ying20041116"
# ========================================================

options = Options()
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--disable-popup-blocking")

service = Service(ChromeDriverManager().install())
driver = None


def parse_courses(text):
    return [code.strip() for code in text.replace(',', '\n').split('\n') if code.strip()]


def wait_until_start_time():
    """
    等待直到 ATTACK_TIME 到達
    """
    target = datetime.strptime(select_TIME, "%Y-%m-%d %H:%M:%S")
    print(f"[{datetime.now()}] ⏳ 程式待命與倒數中...")
    print(f"目標登入時間：{select_TIME}")

    while True:
        now = datetime.now()
        if now >= target:
            print("\n時間到！啟動瀏覽器並開始登入！")
            break

        # 時間倒數
        remaining = target - now
        print(f"\r還剩 {remaining.seconds} 秒啟動...", end="")
        time.sleep(0.5)


def auto_login_and_navigate():
    global driver
    # 時間到初始化瀏覽器
    driver = webdriver.Chrome(service=service, options=options)

    print(f"[{datetime.now()}] 🚀 正在前往登入頁面...")
    driver.get("https://stucis.ttu.edu.tw/stucismain.php")

    # --- 1. 登入 ---
    try:
        WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_it(1))
        driver.find_element(By.NAME, "ID").send_keys(my_studentID)
        driver.find_element(By.NAME, "PWD").send_keys(my_password)
        driver.find_element(By.XPATH, "//input[@value='登入系統']").click()
        print("登入資訊已送出")
    except Exception as e:
        print("登入過程發生異常 (可能已登入或找不到元素):", e)

    # 等待轉址
    time.sleep(2)

    # --- 2. 尋找選課入口 (selxfer.php) ---
    print("搜尋選課入口...")
    entry_clicked = False
    original_window = driver.current_window_handle

    driver.switch_to.default_content()
    frames = driver.find_elements(By.TAG_NAME, "frame")

    for i in range(len(frames)):
        try:
            driver.switch_to.default_content()
            driver.switch_to.frame(i)
            target_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'selxfer.php')]")
            if target_links:
                driver.execute_script("arguments[0].click();", target_links[0])
                entry_clicked = True
                print("點擊選課系統入口")
                break
        except:
            continue

    if not entry_clicked:
        print("找不到入口，請手動進入選課系統。")

    # --- 3. 切換視窗 ---
    time.sleep(2)
    for window_handle in driver.window_handles:
        if window_handle != original_window:
            driver.switch_to.window(window_handle)
            break

    # --- 4. 快速選課 ---
    try:
        driver.switch_to.default_content()
        try:
            driver.switch_to.frame(0)
        except:
            pass

        # 點上方選單
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//img[contains(@src, 'action.png')]"))).click()

        # 點快速選課
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'FastSelect.php')]"))).click()
        print("已進入 [快速選課] 介面，準備填寫...")

    except Exception as e:
        print("異常:", e)


def execute_textarea_attack():

    course_list = parse_courses(TARGET_COURSES_TEXT)
    BATCH_SIZE = 5
    batches = [course_list[i:i + BATCH_SIZE] for i in range(0, len(course_list), BATCH_SIZE)]

    print("開始執行填寫與送出...")

    for idx, batch in enumerate(batches):
        print(f"\n--- 執行第 {idx + 1} 批次: {batch} ---")

        try:
            # 1. 確保在輸入框Frame
            driver.switch_to.default_content()
            frames = driver.find_elements(By.TAG_NAME, "frame")
            search_indices = [-1] + list(range(len(frames)))
            textarea = None

            for i in search_indices:
                try:
                    driver.switch_to.default_content()
                    if i != -1: driver.switch_to.frame(i)
                    found = driver.find_elements(By.TAG_NAME, "textarea")
                    if found:
                        textarea = found[0]
                        break
                except:
                    continue

            if not textarea:
                print("找不到 textarea 輸入框！")
                continue

            # 2. 組合與填寫
            batch_text = "\n".join(batch)
            print(f"正在填入:\n{batch_text}")

            textarea.clear()
            textarea.send_keys(batch_text)
            driver.execute_script("arguments[0].value = arguments[1];", textarea, batch_text)

            # 3. 送出選課
            try:
                driver.find_element(By.XPATH, "//input[@type='submit']").click()
            except:
                driver.execute_script("document.forms['FastSel'].submit();")

            print(" 已送出！")

            # 等待刷新 (稍微縮短，因為是搶課模式)
            if idx < len(batches) - 1:
                print(" 等待系統回應 (1秒)...")
                time.sleep(1)

        except Exception as e:
            print(f" 發生錯誤: {e}")

    print("\n 選課完成！")
    driver.save_screenshot("final_result.png")


if __name__ == "__main__":
    try:
        # 1. 等待時間
        wait_until_start_time()

        # 2. 時間到 -> 啟動瀏覽器登入
        auto_login_and_navigate()

        # 3. 登入導航完畢 -> 直接執行填寫
        execute_textarea_attack()

    except Exception as e:
        print("主程序錯誤:", e)

    print("\n程式結束，按 Enter 關閉...")
    input()
    if driver:
        driver.quit()