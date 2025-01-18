import cv2
from mosaic_builder.image_stats import get_image_dims


def add_text(image, text: str = ""):
    height, width = get_image_dims(image)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 5
    thickness = 5

    # get text size
    (text_width, text_height), baseline = cv2.getTextSize(
        text, font, font_scale, thickness
    )

    # calc position
    text_x = (width - text_width) // 2
    text_y = height - text_height

    cv2.putText(
        image, text, (text_x, text_y), font, font_scale, (0, 0, 0), thickness + 2
    )  # outline
    cv2.putText(
        image, text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness
    )  # text
