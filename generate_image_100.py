from PIL import Image
import numpy as np

for i in range(100):
    # 随机生成图片尺寸
    width = np.random.randint(300, 2000)
    height = np.random.randint(300, 2000)
    # 创建随机颜色的图片
    img_array = np.random.rand(height, width, 3) * 255
    img = Image.fromarray(img_array.astype('uint8')).convert('RGB')
    img.save(f'test_{i}.jpg')