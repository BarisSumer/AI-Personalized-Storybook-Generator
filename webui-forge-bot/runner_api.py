# runner_api.py
from __future__ import annotations
import base64, io, json, time, hashlib, os, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests
from PIL import Image
import pandas as pd

# ----------------- Yardımcılar -----------------
_VALID_IMG_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

def _b64_image_from_path(p: Path) -> str:
    img = Image.open(p).convert("RGB")
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def _to_data_url(b64: str) -> str:
    return b64 if b64.startswith("data:image") else f"data:image/png;base64,{b64}"

def _clamp_dim(v: int) -> int:
    v = max(64, min(2048, int(v)))
    return v - (v % 8)

def _get(api: str, path: str) -> Dict[str, Any]:
    r = requests.get(f"{api}{path}", timeout=30); r.raise_for_status(); return r.json()

def _post(api: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(f"{api}{path}", json=payload, timeout=600); r.raise_for_status(); return r.json()

def _sha1_of_b64(b64_plain: str) -> str:
    try: return hashlib.sha1(base64.b64decode(b64_plain)).hexdigest()
    except Exception: return ""

def _save_b64(b64_plain: str, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f: f.write(base64.b64decode(b64_plain))

# ----------------- Excel / Placeholder -----------------
def _normalize_gender_token(raw: Optional[str]) -> str:
    if not raw: return "boy"
    s = str(raw).strip().lower()
    if re.search(r"kız|kiz|female|woman|girl|kadın|kadin|f", s): return "girl"
    if re.search(r"erkek|male|man|boy|e", s): return "boy"
    return "boy"

def _load_excel(path: Optional[str]) -> Optional[pd.DataFrame]:
    if not path: return None
    try:
        if str(path).lower().endswith(".csv"):
            return pd.read_csv(path, encoding="utf-8-sig")
        return pd.read_excel(path)
    except Exception:
        try: return pd.read_excel(path, engine="openpyxl")
        except Exception: return None

def _resolve_gender_for_face(df: Optional[pd.DataFrame], settings: Dict[str, Any], face_path: Path) -> str:
    if df is None: return "boy"
    col_photo = (settings.get("col_photo") or "@photo")
    try: series = df[col_photo].astype(str).str.lower()
    except Exception: return "boy"
    face_abs = str(face_path).lower(); fname = face_path.name.lower()
    hit = df[series == face_abs]
    if hit.empty: hit = df[series.str.contains(re.escape(fname), na=False)]
    if hit.empty: return "boy"
    row = hit.iloc[0]
    for key in row.index:
        kl = str(key).strip().lower()
        if kl in ("cinsiyet","gender","sex") or "cins" in kl or "gender" in kl:
            return _normalize_gender_token(row.get(key))
    return "boy"

def _apply_placeholders(text: str, gender_token: str) -> str:
    return (text or "").replace("{Cinsiyet}", gender_token)

# ----------------- ControlNet Units -----------------
def _compute_processor_res(w: int, h: int) -> int:
    # 1020x1980 gibi geniş görüntülerde daha güçlü koşullama için:
    short = min(_clamp_dim(w), _clamp_dim(h))
    return max(384, min(1024, short))

# ------- ControlNet Unit kurucu (Forge UI ile birebir alanlar) -------
def _build_cnet_units(
    face_b64_plain: str,
    pose_b64_plain: Optional[str],
    cn0_module: str, cn0_model: str, cn0_resize: int,
    cn1_module: str, cn1_model: str, cn1_resize: int,
    cn0_weight: float = 0.5, cn1_weight: float = 0.5,
    cn0_mode: int = 0, cn1_mode: int = 0,
    *,
    # DİKKAT: u0 için float, u1 için int
    u0_processor: float = 0.5,   # Instant-ID strength (0.0–1.0)
    u1_processor: int = 512,     # keypoints / pose çözünürlüğü
    pixel_perfect: bool = False,
    guidance_start: float = 0.0,
    guidance_end: float = 1.0,
) -> List[Dict[str, Any]]:
    u0 = {
        "enabled": True,
        "module": cn0_module,
        "model": cn0_model,
        "weight": float(cn0_weight),
        "control_mode": int(cn0_mode),
        "image": face_b64_plain,
        "input_image": face_b64_plain,
        "resize_mode": int(cn0_resize),
        # >>> BURASI FLOAT KALMALI
        "processor_res": float(u0_processor),
        "guidance_start": float(guidance_start),
        "guidance_end": float(guidance_end),
        "pixel_perfect": bool(pixel_perfect),
    }
    u1_img = pose_b64_plain if pose_b64_plain else face_b64_plain
    u1 = {
        "enabled": True,
        "module": cn1_module,
        "model": cn1_model,
        "weight": float(cn1_weight),
        "control_mode": int(cn1_mode),
        "image": u1_img,
        "input_image": u1_img,
        "resize_mode": int(cn1_resize),
        # >>> BURASI INT KALMALI
        "processor_res": int(u1_processor),
        "guidance_start": float(guidance_start),
        "guidance_end": float(guidance_end),
        "pixel_perfect": bool(pixel_perfect),
    }
    return [u0, u1]



# ------- txt2img: Forge UI parametre eşleşmeli payload -------
def _txt2img(
    *,
    api_base: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
    sampler: str,
    steps: int,
    width: int,
    height: int,
    cfg_scale: float,
    use_controlnet: bool,
    face_b64_plain: Optional[str],
    checkpoint: Optional[str] = None,
    use_reactor: bool = False,                 # only if alwayson_scripts ile kullanacaksan
    cn_args: Optional[List[Dict[str, Any]]] = None,
    styles: Optional[List[str]] = None,
    # ek: highres kapalıyken Forge defaultları
    tiling: bool = False,
    s_churn: float = 0.0,
    s_tmin: float = 0.0,
    s_tmax: Optional[float] = None,
    s_noise: float = 1.0,
) -> Dict[str, Any]:
    _set_checkpoint_if_needed(api_base, checkpoint)

    # Forge’un txt2img JSON’una denk gelen çekirdek alanlar
    payload: Dict[str, Any] = {
        "prompt": prompt or "",
        "negative_prompt": negative_prompt or "",
        "seed": int(seed),                      # -1 ise backend rastgele üretir
        "sampler_name": sampler,                # örn: "DPM++ 2M"
        "steps": int(steps),
        "width": _clamp_dim(width),
        "height": _clamp_dim(height),
        "cfg_scale": float(cfg_scale),
        "batch_size": 1,
        "n_iter": 1,
        "restore_faces": False,
        "enable_hr": False,                    # HR kapalı (UI ile eşleşiyor)
        "tiling": bool(tiling),
        # K-Sampler gelişmiş (Forge varsayılanlarına paralel)
        "s_churn": float(s_churn),
        "s_tmin": float(s_tmin),
        "s_tmax": (None if s_tmax is None else float(s_tmax)),
        "s_noise": float(s_noise),
        # SDXL metadata (Forge kendisi doldurabiliyor; boş kalsa sorun olmaz)
        "override_settings": {},
        "override_settings_restore_afterwards": True,
    }

    if styles:
        payload["styles"] = list(styles)

    # ControlNet alwayson_scripts
    if use_controlnet and cn_args:
        payload.setdefault("alwayson_scripts", {})["ControlNet"] = {"args": cn_args}

    # REActor’ı aynı graf içine almak istersen (genelde post-process önerilir)
    if use_reactor and face_b64_plain:
        aos = _reactor_alwayson_payload_from_scriptinfo(api_base, face_b64_plain)
        if aos:
            payload.setdefault("alwayson_scripts", {}).update(aos)

    return _post(api_base, "/sdapi/v1/txt2img", payload)

# ----------------- REActor -----------------
def _reactor_available(api_base: str) -> bool:
    for path in ("/reactor/ping", "/reactor/models", "/reactor/model_list"):
        try:
            r = requests.get(f"{api_base}{path}", timeout=5)
            if r.ok: return True
        except Exception: pass
    return False

def _reactor_models(api_base: str) -> List[str]:
    try:
        r = _get(api_base, "/reactor/models")
        if isinstance(r, dict) and "models" in r: return r["models"]
        if isinstance(r, list): return r
    except Exception: pass
    return []

def _reactor_swap_image(
    api_base: str,
    source_b64_plain: str,
    target_b64_plain: str,
    *,
    model: str = "inswapper_128.onnx",
    face_index: int = -1,             # -1 = en büyük/yakalanan yüz (UI'ye yakın davranış)
    source_face_index: int = 0,
    # Dokümandaki gelişmiş parametreler (UI ile aynı defaultlar)
    upscaler: str = "None",
    scale: int = 1,
    upscale_visibility: float = 1.0,
    face_restorer: str = "None",
    restorer_visibility: float = 1.0,  # UI sıklıkla 1.0
    codeformer_weight: float = 0.5,
    restore_first: int = 1,            # Doküman: 1 → önce restore sonra swap
    gender_source: int = 0,
    gender_target: int = 0,
    device: str = "CPU",               # varsa "CUDA"
    mask_face: int = 0,                # 1 yaparsan sadece yüz alanını maskeleyerek uygular
    select_source: int = 0,
    face_model: str = "None",
    source_folder: str = "",
    random_image: int = 0,
    upscale_force: int = 0,
    det_thresh: float = 0.5,
    det_maxnum: int = 0,
    save_to_file: int = 0,
    result_file_path: str = "",
) -> str:
    """
    REActor harici API (doküman uyumlu). PLAIN base64 döner.
    """
    payload = {
        "source_image": _to_data_url(source_b64_plain),
        "target_image": _to_data_url(target_b64_plain),

        # Dokümanda listeler kullanılıyor:
        "source_faces_index": [int(source_face_index)],
        "face_index": [int(face_index)],

        "upscaler": upscaler,
        "scale": int(scale),
        "upscale_visibility": float(upscale_visibility),

        "face_restorer": face_restorer,
        "restorer_visibility": float(restorer_visibility),
        "codeformer_weight": float(codeformer_weight),
        "restore_first": int(restore_first),

        "model": model,
        "gender_source": int(gender_source),
        "gender_target": int(gender_target),

        "save_to_file": int(save_to_file),
        "result_file_path": result_file_path,

        "device": device,              # "CPU" | "CUDA"
        "mask_face": int(mask_face),
        "select_source": int(select_source),
        "face_model": face_model,
        "source_folder": source_folder,
        "random_image": int(random_image),
        "upscale_force": int(upscale_force),
        "det_thresh": float(det_thresh),
        "det_maxnum": int(det_maxnum),
    }

    resp = _post(api_base, "/reactor/image", payload)

    # Dönüş anahtarları farklı sürümlerde değişebiliyor:
    out = resp.get("image")
    if not out:
        imgs = resp.get("images") or []
        out = imgs[0] if imgs else None
    if not out:
        out = resp.get("result")
    if not out:
        raise RuntimeError(f"REActor boş döndü: {json.dumps(resp)[:200]}")

    # Data URL ise PLAIN’e indir
    if out.startswith("data:image"):
        out = out.split(",", 1)[-1]
    return out

def _reactor_alwayson_payload_from_scriptinfo(api_base: str, face_b64_plain: str) -> Optional[Dict[str, Any]]:
    """
    UI’daki gibi REActor’ı txt2img sırasında alwayson_scripts olarak ekler.
    Script-info’dan arg şablonunu alıp 'enabled', 'source_image', 'swap_in_loop' vb. alanları set eder.
    """
    try: info = _get(api_base, "/sdapi/v1/script-info")
    except Exception: return None
    aos = info.get("alwayson_scripts") or {}
    key, spec = None, None
    for k, v in aos.items():
        title = (v.get("title") or k or "").lower()
        if "reactor" in title: key, spec = k, v; break
    if not key: return None

    args_spec: List[Dict[str, Any]] = spec.get("args") or []
    args: List[Any] = []
    for a in args_spec:
        name = (a.get("label") or a.get("name") or "").lower()
        default = a.get("default")
        val = default
        if "enable" in name: val = True
        elif "source" in name and "image" in name: val = _to_data_url(face_b64_plain)
        elif "swap" in name and "loop" in name: val = True
        args.append(val)

    return {"alwayson_scripts": { key: { "args": args } }}

# ----------------- txt2img -----------------
def _set_checkpoint_if_needed(api_base: str, checkpoint_name: Optional[str]) -> None:
    if not checkpoint_name: return
    try:
        _post(api_base, "/sdapi/v1/options", {"sd_model_checkpoint": checkpoint_name})
        time.sleep(0.5)
    except Exception as e:
        print(f"[WARN] Checkpoint ayarlanamadı: {e}")

def _txt2img(
    api_base: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
    sampler: str,
    steps: int,
    width: int,
    height: int,
    cfg_scale: float,
    use_controlnet: bool,
    face_b64_plain: Optional[str],
    checkpoint: Optional[str] = None,
    reactor_in_loop: bool = False,         # <<< yeni
    cn_args: Optional[List[Dict[str, Any]]] = None,
    styles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    _set_checkpoint_if_needed(api_base, checkpoint)

    payload: Dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt or "",
        "seed": int(seed),
        "sampler_name": sampler,
        "steps": int(steps),
        "width": _clamp_dim(width),
        "height": _clamp_dim(height),
        "cfg_scale": float(cfg_scale),
        "batch_size": 1,
        "n_iter": 1,
        "restore_faces": False,
        "enable_hr": False,
    }
    if styles: payload["styles"] = list(styles)
    if use_controlnet and cn_args:
        payload.setdefault("alwayson_scripts", {}).update({"ControlNet": {"args": cn_args}})
    if reactor_in_loop and face_b64_plain:
        aos = _reactor_alwayson_payload_from_scriptinfo(api_base, face_b64_plain)
        if aos: payload.setdefault("alwayson_scripts", {}).update(aos)

    return _post(api_base, "/sdapi/v1/txt2img", payload)

# ----------------- Ana çağırıcı -----------------
def run_book_via_api(
    book: Dict[str, Any],
    pages: List[Dict[str, Any]],
    faces_dir: str = r"C:\faces",
    poses_dir: str = r"C:\poses",
    out_dir: Optional[str] = None,
    api_base: str = "http://127.0.0.1:7861",
    debug_save_prepost: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True, "items": []}

    title      = book.get("title") or book.get("name") or "book"
    settings   = book.get("settings") or {}
    df_excel   = _load_excel(settings.get("excel_path"))
    book_neg   = book.get("negative_prompt", "")
    book_smpl  = book.get("sampler", "Euler a")
    book_steps = int(book.get("steps", 20))
    book_w     = int(book.get("width", 1024))
    book_h     = int(book.get("height", 576))
    book_cfg   = float(book.get("cfg_scale", 7.0))
    book_ckpt  = book.get("checkpoint")
    book_pose_default = book.get("poses_dir") or poses_dir

    face_paths = sorted([p for p in Path(faces_dir).rglob("*.*") if p.suffix.lower() in _VALID_IMG_SUFFIXES])

    base_out = Path(out_dir) if out_dir else (Path.cwd() / "outputs")
    base_out.mkdir(parents=True, exist_ok=True)

    reactor_ok = _reactor_available(api_base)
    r_models = _reactor_models(api_base) if reactor_ok else []
    print(f"[INFO] API: {api_base} | REActor: {'OK' if reactor_ok else 'YOK'} | Models: {r_models[:3]}{'...' if len(r_models)>3 else ''}")
    print(f"[INFO] Başlıyor: {title} | faces:{len(face_paths)} pages:{len(pages)}")

    for ci, fpath in enumerate(face_paths, start=1):
        face_b64_plain = _b64_image_from_path(fpath)
        child_name = fpath.stem
        child_out = base_out / f"{title}-{child_name}"
        child_out.mkdir(parents=True, exist_ok=True)
        gender = _resolve_gender_for_face(df_excel, settings, fpath)

        for pi, page in enumerate(pages, start=1):
            raw_prompt = (page.get("prompt") or "").strip()
            raw_neg    = (page.get("negative_prompt") or book_neg).strip()
            prompt     = _apply_placeholders(raw_prompt, gender)
            neg_prompt = _apply_placeholders(raw_neg, gender)

            seed       = int(page.get("seed", -1))
            sampler    = page.get("sampling_method") or book_smpl
            steps      = int(page.get("sampling_steps", book_steps))
            width      = int(page.get("width",  book_w))
            height     = int(page.get("height", book_h))
            cfg_scale  = float(page.get("cfg_scale", book_cfg))
            checkpoint = page.get("checkpoint") or book_ckpt or None
            styles     = page.get("styles") or []

            use_cnet       = bool(page.get("use_controlnet", True))
            use_reactor    = bool(page.get("use_reactor", False))
            reactor_model  = page.get("reactor_model", "inswapper_128.onnx")
            reactor_fidx   = int(page.get("reactor_face_index", -1))
            reactor_s_fidx = int(page.get("reactor_source_face_index", -1))

            # POSE
            pose_source = (page.get("pose_path") or book_pose_default or poses_dir or "").strip()
            pose_b64_plain: Optional[str] = None
            if pose_source:
                pth = Path(pose_source)
                if pth.is_dir():
                    for n in sorted(pth.iterdir()):
                        if n.suffix.lower() in _VALID_IMG_SUFFIXES:
                            pose_b64_plain = _b64_image_from_path(n); break
                elif pth.exists():
                    pose_b64_plain = _b64_image_from_path(pth)

            # ControlNet units (Forge ile hizalı)
            cn_args: Optional[List[Dict[str, Any]]] = None
            if use_cnet:
                proc_res = _compute_processor_res(width, height)
                cn_args = _build_cnet_units(
                    face_b64_plain=face_b64_plain,
                    pose_b64_plain=pose_b64_plain,
                    cn0_module=page.get("cn0_module", "InsightFace (InstantID)"),
                    cn0_model=page.get("cn0_model", "ip-adapter_instant_id_sdxl [eb2d3ec0]"),
                    cn0_resize=int(page.get("cn0_resize", 0)),
                    cn1_module=page.get("cn1_module", "instant_id_face_keypoints"),
                    cn1_model=page.get("cn1_model", "control_instant_id_sdxl [c5c25a50]"),
                    cn1_resize=int(page.get("cn1_resize", 1)),
                    cn0_weight=float(page.get("cn0_weight", 0.5)),
                    cn1_weight=float(page.get("cn1_weight", 0.7)),
                    cn0_mode=int(page.get("cn0_mode", 0)),
                    cn1_mode=int(page.get("cn1_mode", 2)),
                    # >>> Instant-ID strength ve keypoints çözünürlüğü
                    u0_processor=float(page.get("cn0_processor", 0.5)),
                    u1_processor=int(page.get("cn1_processor", 512)),
                    pixel_perfect=False,
                    guidance_start=0.0,
                    guidance_end=1.0,
                )

            print(f"[GEN] child={child_name} page={pi} seed={seed} sampler={sampler} steps={steps} "
                  f"{width}x{height} cfg={cfg_scale} cnet={use_cnet} reactor={use_reactor}")

            try:
                # 1) Üretimde de REActor’ı tak (UI davranışı)
                resp = _txt2img(
                    api_base=api_base,
                    prompt=prompt,
                    negative_prompt=neg_prompt,
                    seed=seed,
                    sampler=sampler,
                    steps=steps,
                    width=width,
                    height=height,
                    cfg_scale=cfg_scale,
                    use_controlnet=use_cnet,
                    face_b64_plain=face_b64_plain,
                    checkpoint=checkpoint,
                    reactor_in_loop=(use_reactor and reactor_ok),
                    cn_args=cn_args,
                    styles=styles,
                )
                images = resp.get("images") or []
                if not images: raise RuntimeError("API boş döndü")
                gen_b64_plain = images[0].split(",", 1)[-1]
                pre_hash = _sha1_of_b64(gen_b64_plain)

                if debug_save_prepost:
                    _save_b64(gen_b64_plain, child_out / f"sayfa{pi}_pre.png")

                # 2) Post-process REActor (ek temkin)
                final_b64_plain = gen_b64_plain
                swapped_ok = False
                if use_reactor and reactor_ok:
                    try:
                        swapped = _reactor_swap_image(
                            api_base=api_base,
                            source_b64_plain=face_b64_plain,
                            target_b64_plain=gen_b64_plain,
                            model=page.get("reactor_model", "inswapper_128.onnx"),
                            face_index=int(page.get("reactor_face_index", -1)),
                            source_face_index=int(page.get("reactor_source_face_index", 0)),
                            device=page.get("reactor_device", "CPU"),
                            mask_face=int(page.get("reactor_mask_face", 0)),
                            restore_first=int(page.get("reactor_restore_first", 1)),
                            restorer_visibility=float(page.get("reactor_restorer_visibility", 1.0)),
                            codeformer_weight=float(page.get("reactor_codeformer_weight", 0.5)),
                            det_thresh=float(page.get("reactor_det_thresh", 0.5)),
                            det_maxnum=int(page.get("reactor_det_maxnum", 0)),
                        )

                        post_hash = _sha1_of_b64(swapped)
                        if post_hash and post_hash != pre_hash:
                            final_b64_plain = swapped; swapped_ok = True
                            print("[REACTOR] swap uygulandı (hash değişti).")
                        else:
                            print("[REACTOR] yüz bulunamadı/değişmedi (hash aynı).")
                        if debug_save_prepost:
                            _save_b64(swapped, child_out / f"sayfa{pi}_post.png")
                    except Exception as e:
                        print(f"[WARN] REActor post-process hata: {e}")

                # 3) Kaydet
                out_path = child_out / f"sayfa{pi}.png"
                _save_b64(final_b64_plain, out_path)
                out["items"].append(str(out_path))
                print(f"[OK] Kaydedildi: {out_path} {'(swap)' if swapped_ok else '(no-swap)'}")

            except Exception as e:
                out["ok"] = False
                print(f"[ERR] child={child_name} page={pi}: {e}")

    return out
