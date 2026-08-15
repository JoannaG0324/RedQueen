import sys
import random
from tqdm import tqdm


def tt():
    total_page = 20

    for page in tqdm(range(2, total_page + 1), leave=False):
            # page_delay = random.uniform(5, 15)
            msg = f"  等待 秒后获取第 {page}/{total_page} 页..."
            # \r 光标回到行首，end="" 不换行，stdout实时刷新
            sys.stdout.write(f"\r{msg}")
            sys.stdout.flush()   # 强制刷新缓冲区，立刻打印，不要等缓冲区满

    sys.stdout.write("\r" + " "*120 + "\r")
    sys.stdout.flush()


if __name__ == "__main__":
    tt()    
