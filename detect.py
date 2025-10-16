# 使用原生YOLOv5代码进行目标检测
"""使用YOLOv5原生代码进行摄像头实时目标检测，不依赖ultralytics库."""

import argparse
import csv
import logging
import os
import sys
import time
import traceback
from pathlib import Path

import cv2
import torch

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/detect_debug.log"), logging.StreamHandler()],
)
logger = logging.getLogger("detect")

# 获取项目根目录
FILE = Path(__file__).resolve()
ROOT = FILE.parents[0]  # YOLOv5 root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

# COCO数据集类别名称
COCO_NAMES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]

# 确保logs目录存在
os.makedirs("logs", exist_ok=True)


# 记录到CSV文件的函数
def log_to_csv(status, message):
    """记录操作到CSV日志文件."""
    csv_path = "logs/detection_log.csv"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, status, message])
    except Exception as e:
        logger.error(f"无法写入CSV日志: {str(e)}")


def parse_opt():
    """解析命令行参数."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, default="yolov5s.pt", help="模型权重文件路径")
    parser.add_argument("--source", type=str, default="0", help="输入源 (0 for webcam)")
    parser.add_argument("--conf-thres", type=float, default=0.4, help="置信度阈值")
    parser.add_argument("--iou-thres", type=float, default=0.45, help="IoU阈值")
    parser.add_argument("--classes", nargs="+", type=int, help="要检测的类别ID列表")
    parser.add_argument("--view-img", action="store_true", default=True, help="显示检测结果")
    parser.add_argument("--no-view", action="store_true", help="不显示检测结果")
    parser.add_argument("--save-txt", action="store_true", help="保存结果到txt文件")
    parser.add_argument("--no-save", action="store_true", help="不保存检测结果")
    parser.add_argument("--max-frames", type=int, default=0, help="最大处理帧数 (0表示无限)")
    parser.add_argument("--timeout", type=int, default=0, help="运行超时时间(秒) (0表示无限)")
    return parser.parse_args()


def load_model(weights, device=""):
    """加载YOLOv5模型."""
    try:
        # 导入必要的YOLOv5模块
        from models.experimental import attempt_load
        from utils.torch_utils import select_device

        # 选择设备
        device = select_device(device)
        logger.info(f"使用设备: {device}")

        # 加载模型
        logger.info(f"加载模型: {weights}")
        model = attempt_load(weights, device=device)
        model.eval()  # 设置为评估模式

        # 获取模型的输入大小
        stride = int(model.stride.max())
        names = COCO_NAMES  # 使用COCO类别名称

        logger.info(f"模型加载成功，步长: {stride}")
        log_to_csv("模型加载", f"成功加载模型: {weights}")
        return model, device, stride, names
    except Exception as e:
        error_msg = f"加载模型失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        log_to_csv("模型加载", error_msg)
        raise


def letterbox(img, new_shape=(640, 640), color=(114, 114, 114), auto=True):
    """调整图像大小，保持纵横比，添加填充."""
    shape = img.shape[:2]  # current shape [height, width]

    # 如果new_shape是一个整数，则将高度和宽度都设为该值
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # 计算缩放比例
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])

    # 计算调整后的图像尺寸
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))

    # 计算填充
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding

    # 如果auto为True，则最小化填充
    if auto:
        dw, dh = dw % 64, dh % 64  # wh padding

    dw /= 2  # 平均左右填充
    dh /= 2  # 平均上下填充

    # 调整图像大小
    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

    # 添加填充
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

    return img


def process_image(img, device, img_size=640):
    """处理单张图像，准备输入模型."""
    try:
        # 调整图像大小
        img0 = img.copy()
        img = letterbox(img0, img_size, auto=True)

        # 转换为RGB和张量
        img = img[:, :, ::-1].transpose(2, 0, 1)  # BGR to RGB, to 3x416x416
        img = img.copy()  # 创建副本以避免负步长问题
        img = torch.from_numpy(img).to(device)
        img = img.float()  # uint8 to fp16/32
        img /= 255.0  # 0 - 255 to 0.0 - 1.0
        if len(img.shape) == 3:
            img = img[None]  # 添加批次维度

        return img, img0
    except Exception as e:
        logger.error(f"处理图像失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise


def detect_objects(img, model, device, conf_thres=0.4, iou_thres=0.45, classes=None):
    """执行目标检测."""
    try:
        # 导入必要的函数
        from utils.general import non_max_suppression

        # 前向传播
        pred = model(img)

        # 应用非极大值抑制
        pred = non_max_suppression(pred, conf_thres, iou_thres, classes=classes)

        return pred
    except Exception as e:
        logger.error(f"检测对象失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise


def annotate_frame(img0, pred, img_shape, names, line_thickness=3):
    """在图像上绘制检测结果."""
    try:
        # 导入必要的函数
        from utils.general import scale_coords

        # 处理检测结果
        im0 = img0.copy()

        for i, det in enumerate(pred):  # 处理每个图像
            if len(det):
                # 将坐标从img_size缩放到原始图像尺寸
                det[:, :4] = scale_coords(img_shape, det[:, :4], im0.shape).round()

                # 在图像上绘制边界框
                for *xyxy, conf, cls in reversed(det):
                    # 确保坐标是整数类型
                    xyxy = [int(x.item()) if hasattr(x, "item") else int(x) for x in xyxy]
                    c = int(cls.item() if hasattr(cls, "item") else cls)  # 类别
                    label = f"{names[c]} {conf.item():.2f}" if hasattr(conf, "item") else f"{names[c]} {conf:.2f}"

                    # 直接使用OpenCV绘制边界框
                    try:
                        cv2.rectangle(im0, (xyxy[0], xyxy[1]), (xyxy[2], xyxy[3]), (0, 255, 0), line_thickness)
                        cv2.putText(im0, label, (xyxy[0], xyxy[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    except Exception as e:
                        logger.error(f"绘制边界框失败: {str(e)}")
                        logger.error(f"坐标值: {xyxy}")

        return im0
    except Exception as e:
        logger.error(f"标注图像失败: {str(e)}")
        logger.error(traceback.format_exc())
        # 如果标注失败，返回原始图像
        return img0


def run(
    weights="yolov5s.pt",
    source="0",
    conf_thres=0.4,
    iou_thres=0.45,
    classes=None,
    view_img=True,
    save_txt=False,
    no_save=False,
    max_frames=0,
    timeout=0,
):
    """运行目标检测."""
    cap = None
    try:
        logger.info("开始目标检测")
        log_to_csv("检测开始", f"源: {source}, 置信度阈值: {conf_thres}")

        # 加载模型
        model, device, stride, names = load_model(weights)

        # 检查是否显示图像
        if no_save:
            view_img = False

        # 打开摄像头
        cap = cv2.VideoCapture(int(source) if source.isnumeric() else source)
        if not cap.isOpened():
            error_msg = f"无法打开摄像头: {source}"
            logger.error(error_msg)
            log_to_csv("摄像头错误", error_msg)
            raise Exception(error_msg)

        logger.info(f"成功打开摄像头: {source}")
        log_to_csv("摄像头初始化", f"成功打开摄像头: {source}")

        # 初始化计数器和计时器
        frame_count = 0
        start_time = time.time()

        # 主循环
        while True:
            # 检查超时
            if timeout > 0 and (time.time() - start_time) > timeout:
                logger.info(f"检测超时 ({timeout}秒)，退出")
                log_to_csv("检测结束", f"超时退出 ({timeout}秒)")
                break

            # 检查最大帧数
            if max_frames > 0 and frame_count >= max_frames:
                logger.info(f"达到最大帧数 ({max_frames})，退出")
                log_to_csv("检测结束", f"达到最大帧数退出 ({max_frames})")
                break

            # 读取帧
            ret, frame = cap.read()
            if not ret:
                logger.error("无法读取摄像头帧")
                log_to_csv("帧读取错误", "无法读取摄像头帧")
                # 尝试重新打开摄像头
                cap.release()
                time.sleep(1)
                cap = cv2.VideoCapture(int(source) if source.isnumeric() else source)
                if not cap.isOpened():
                    logger.error("无法重新打开摄像头")
                    log_to_csv("摄像头错误", "无法重新打开摄像头")
                    break
                continue

            # 处理图像
            img, img0 = process_image(frame, device)

            # 执行检测
            pred = detect_objects(img, model, device, conf_thres, iou_thres, classes)

            # 标注图像
            annotated_frame = annotate_frame(img0, pred, img.shape[2:], names)

            # 显示结果
            if view_img:
                cv2.imshow("YOLOv5 Detection", annotated_frame)
                key = cv2.waitKey(1)
                if key == 27:  # ESC键退出
                    logger.info("用户按ESC键退出")
                    log_to_csv("检测结束", "用户按ESC键退出")
                    break
                elif key == ord("q"):  # 'q'键也可以退出
                    logger.info("用户按Q键退出")
                    log_to_csv("检测结束", "用户按Q键退出")
                    break

            # 增加帧计数
            frame_count += 1

            # 每10帧记录一次信息
            if frame_count % 10 == 0:
                logger.info(f"已处理 {frame_count} 帧")

    except KeyboardInterrupt:
        logger.info("检测被用户中断")
        log_to_csv("检测结束", "用户中断")
    except Exception as e:
        error_msg = f"检测过程中发生错误: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        log_to_csv("检测错误", error_msg)
        raise
    finally:
        # 清理资源
        if cap is not None and cap.isOpened():
            cap.release()
        cv2.destroyAllWindows()
        logger.info("检测结束，资源已释放")
        log_to_csv("资源清理", "摄像头和窗口已释放")


def main(opt):
    """主函数."""
    try:
        logger.info(f"命令行参数: {vars(opt)}")

        # 检查是否显示图像
        view_img = opt.view_img and not opt.no_view

        # 运行检测
        run(
            weights=opt.weights,
            source=opt.source,
            conf_thres=opt.conf_thres,
            iou_thres=opt.iou_thres,
            classes=opt.classes,
            view_img=view_img,
            save_txt=opt.save_txt,
            no_save=opt.no_save,
            max_frames=opt.max_frames,
            timeout=opt.timeout,
        )
        return 0
    except Exception as e:
        logger.error(f"主函数执行失败: {str(e)}")
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    try:
        logger.info("程序启动")
        # 解析命令行参数
        opt = parse_opt()
        # 运行主函数
        sys.exit(main(opt))
    except Exception as e:
        logger.critical(f"程序运行失败: {str(e)}")
        logger.critical(traceback.format_exc())
        sys.exit(1)
