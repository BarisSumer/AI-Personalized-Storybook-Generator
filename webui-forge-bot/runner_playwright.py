# runner_playwright.py
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

WEBUI_URL = "http://127.0.0.1:7861"  # Stable Diffusion WebUI/Forge/SD.Next adresiniz

# ---------- küçük yardımcılar ----------
def _scroll(loc):
    try:
        loc.scroll_into_view_if_needed(timeout=4000)
    except PWTimeout:
        pass

def _fill_num(loc, value):
    _scroll(loc)
    try:
        loc.fill(str(value), timeout=4000)
    except PWTimeout:
        # bazı gradio inputlarında fill görünürlük takılıyor; JS ile yaz
        loc.evaluate(
            "(el, val) => { el.value = val; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
            str(value),
        )

def _click(loc, force=False):
    _scroll(loc)
    loc.click(timeout=4000, force=force)

def _check(loc, want=True):
    _scroll(loc)
    try:
        if want:
            loc.check(timeout=4000)
        else:
            loc.uncheck(timeout=4000)
    except:
        # bazı temalarda .check/.uncheck çalışmıyor
        _click(loc, force=True)

# ---------- sayfayı hazırlama ----------
def _open_ui(page):
    page.set_viewport_size({"width": 1920, "height": 1200})
    print(f"[NAV] {WEBUI_URL}")
    page.goto(WEBUI_URL, wait_until="domcontentloaded")
    page.wait_for_selector("button:has-text('Generate')", timeout=20000)
    print("[READY] UI hazır (buton: button:has-text('Generate'))")
    # txt2img sekmesi
    try:
        _click(page.locator("button[role='tab']:has-text('txt2img'), button[role='tab']:has-text('Txt2img')").first)
        print("[OK] txt2img sekmesine geçildi (button[role='tab']:has-text('txt2img'))")
    except PWTimeout:
        pass

def _ensure_cnet_open(page):
    # ControlNet/ControlNet Integrated akordeonunu aç
    try:
        _click(page.locator("button:has-text('ControlNet Integrated'), button:has-text('ControlNet')").first)
    except PWTimeout:
        pass

def _open_unit(page, idx:int):
    # Unit başlığına tıkla ki içi görünür olsun
    try:
        enabled = page.locator(f"#txt2img_controlnet_ControlNet-{idx}_controlnet_enable_checkbox input[type='checkbox']")
        if not enabled.is_visible():
            _click(page.locator(f"text=/ControlNet Unit {idx}\\b|ControlNet Unit {idx} \\[Instant-ID\\]/i").first)
    except:
        pass

def _cfg_cnet_instant_id(page, idx:int, face_path:Path|None, pose_json:Path|None):
    prefix = f"#txt2img_controlnet_ControlNet-{idx}"
    _open_unit(page, idx)

    # enable + pixel perfect
    _check(page.locator(f"{prefix}_controlnet_enable_checkbox input[type='checkbox']"), True)
    try:
        _check(page.locator(f"{prefix}_controlnet_pixel_perfect_checkbox input[type='checkbox']"), True)
    except:
        pass

    # Control Type -> Instant-ID
    try:
        _click(page.locator(f"{prefix}_controlnet_type_filter_radio label:has-text('Instant-ID')"))
    except:
        pass

    # preprocessor & model
    if idx == 0:
        # Unit 0: InsightFace + ip-adapter_instant_id_sdxl
        try:
            _click(page.locator(f"{prefix}_controlnet_preprocessor_dropdown input[role='listbox']").first)
            _click(page.locator("div[role='option']:has-text('InsightFace (InstantID)')").first)
        except:
            pass
        try:
            _click(page.locator(f"{prefix}_controlnet_model_dropdown input[role='listbox']").first)
            _click(page.locator("div[role='option']:has-text('ip-adapter_instant_id_sdxl')").first)
        except:
            pass
    else:
        # Unit 1: instant_id_face_keypoints + control_instant_id_sdxl
        try:
            _click(page.locator(f"{prefix}_controlnet_preprocessor_dropdown input[role='listbox']").first)
            _click(page.locator("div[role='option']:has-text('instant_id_face_keypoints')").first)
        except:
            pass
        try:
            _click(page.locator(f"{prefix}_controlnet_model_dropdown input[role='listbox']").first)
            _click(page.locator("div[role='option']:has-text('control_instant_id_sdxl')").first)
        except:
            pass

    # control weight = 1
    try:
        _fill_num(page.locator(f"{prefix}_controlnet_control_weight_slider input[type='number']").first, 1)
    except:
        pass

    # Resize and Fill
    try:
        _click(page.locator(f"{prefix}_controlnet_resize_mode_radio label:has-text('Resize and Fill')"))
    except:
        pass

    # dosya yüklemeleri
    if face_path and face_path.exists():
        try:
            fi = page.locator(f"{prefix}_input_image input[type='file']").first
            _scroll(fi)
            fi.set_input_files(str(face_path))
        except:
            print("[WARN] CNet Unit0 yüz yüklenemedi")
    if pose_json and pose_json.exists():
        # bazı sürümlerde poz için ayrı input olmayabilir; varsa set et
        try:
            pi = page.locator(f"{prefix} .cnet-upload-pose input[type='file']").first
            _scroll(pi)
            pi.set_input_files(str(pose_json))
        except:
            pass

def _fill_txt2img(page, pos_prompt, neg_prompt, seed, width, height, steps, cfg):
    # promptlar
    try:
        _scroll(page.locator("#txt2img_prompt"))
        page.locator("#txt2img_prompt textarea, #txt2img_prompt").first.fill(pos_prompt)
        print("[OK] (fallback) #txt2img_prompt ->", pos_prompt[:120])
    except Exception as e:
        print("[WARN] prompt doldurulamadı:", e)

    try:
        _scroll(page.locator("#txt2img_neg_prompt"))
        page.locator("#txt2img_neg_prompt textarea, #txt2img_neg_prompt").first.fill(neg_prompt)
        print("[OK] (fallback) #txt2img_neg_prompt ->", neg_prompt[:120])
    except Exception as e:
        print("[WARN] negative doldurulamadı:", e)

    # sayısal alanlar
    try:
        _fill_num(page.locator("#txt2img_steps input[type='number'], #txt2img_steps"), steps)
        print("[OK] (fallback) #txt2img_steps ->", steps)
    except Exception as e:
        print("[WARN] steps doldurulamadı:", e)

    try:
        _fill_num(page.locator("#txt2img_width  input[type='number'], #txt2img_width"), width)
        print("[OK] (fallback) #txt2img_width ->", width)
    except Exception as e:
        print("[WARN] width doldurulamadı:", e)

    try:
        _fill_num(page.locator("#txt2img_height input[type='number'], #txt2img_height"), height)
        print("[OK] (fallback) #txt2img_height ->", height)
    except Exception as e:
        print("[WARN] height doldurulamadı:", e)

    try:
        _fill_num(page.locator("#txt2img_cfg_scale input[type='number'], #txt2img_cfg_scale"), cfg)
        print("[OK] (fallback) #txt2img_cfg_scale ->", cfg)
    except Exception as e:
        print("[WARN] cfg doldurulamadı:", e)

    try:
        _fill_num(page.locator("#txt2img_seed input[type='number'], #txt2img_seed"), seed)
        print("[OK] (fallback) #txt2img_seed ->", seed)
    except Exception as e:
        print("[WARN] seed doldurulamadı:", e)

def _generate(page, timeout_ms=120000):
    _click(page.locator("button:has-text('Generate')").first)
    page.wait_for_selector("img, canvas, .generations, .image-container img", timeout=timeout_ms)

# ---------- dışa açık koşturucu ----------
# --- dosyanın alt kısmında: dışa açık koşturucu ---

def run_book_ui(
    book: dict,
    pages: list,
    faces_dir: str = "C:\\faces",
    poses_dir: str = "C:\\poses",
    out_dir: str | None = None,   # <-- eklendi
    **kwargs                      # <-- fazladan gelenleri yut
):
    # (isterseniz out_dir'i kullanıp son çıktıları kopyalamak için burada ek mantık kurabiliriz)
    faces = sorted([p for p in Path(faces_dir).glob("*.*") if p.suffix.lower() in (".jpg",".jpeg",".png",".webp")])
    poses = sorted([p for p in Path(poses_dir).glob("*.json")])
    if not poses:
        print(f"[WARN] Poz JSON bulunamadı: {poses_dir} (Unit 1 upload atlanabilir)")
    print(f"[INFO] Başlıyor: {book.get('title','(adsız)')} | faces:{len(faces)} poses:{len(poses)} pages:{len(pages)}")
    if out_dir:
        print(f"[INFO] out_dir alındı (şimdilik bilgilendirme): {out_dir}")

    # ... (fonksiyonun geri kalanı aynen kalsın)
    # with sync_playwright() as p:
    #   ...

# ---- app.py bu ismi import ediyor ----
def run_book_in_browser(
    book: dict,
    pages: list,
    faces_dir: str = "C:\\faces",
    poses_dir: str = "C:\\poses",
    out_dir: str | None = None,   # <-- eklendi
    **kwargs                      # <-- fazladan gelenleri yut
):
    """app.py -> /books/<id>/run burada çağırıyor."""
    return run_book_ui(book, pages, faces_dir, poses_dir, out_dir=out_dir, **kwargs)
