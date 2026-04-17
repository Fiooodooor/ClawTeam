import os, sys
import argparse
import enum

class MountX(enum.IntEnum):
    MEV = 1
    MEV_TS = 2

    # magic methods for argparse compatibility

    def __str__(self):
        return self.name.lower()

    def __repr__(self):
        return str(self)

    @staticmethod
    def argparse(s):
        try:
            return MountX[s.upper()]
        except KeyError:
            return s

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('prj', type=MountX.argparse, choices=list(MountX))
    args = parser.parse_args()
    print("Configure env")
    os.system('MEV_LTB_Debug.py {}'.format(args.prj.name))
    print("Configure LTB")
    os.system("Configure_LTB.py")
    print("Resume_boot")
    os.system("Resume_boot.py")
