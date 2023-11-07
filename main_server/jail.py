import os
import sys
import time
import signal
import shutil
from datetime import datetime, timedelta
from subprocess import Popen, CalledProcessError, TimeoutExpired, check_output, STDOUT

class TLEError(Exception):
    pass

class REError(Exception):
    pass

def get_error_str(cmd,returncode):
    if returncode and returncode < 0:
        try:
            return "Command '%s' died with %r." % (
                    cmd, signal.Signals(-returncode))
        except ValueError:
            return "Command '%s' died with unknown signal %d." % (
                    cmd, -returncode)
    else:
        return "Command '%s' returned non-zero exit status %d." % (
                cmd, returncode)


if __name__ == "__main__":
    """
    -t_: time limit
    -ni_: no stdin redirect
    -no_: no stdout redirect
    -tp_: testcase file path
    """
    if len(sys.argv) < 3:
        sys.stderr.write("usage: python -u script.py path filename")
        sys.exit(-1)

    input_file_name = "input.in"
    output_file_name = "output.out"
    path = sys.argv[1]
    target = sys.argv[2]
    timelimit = 3
    for param in sys.argv[3:]:
        if param.startswith("-t_"):
            try:
                timelimit = int(param[3:])
            except:
                try:
                    timelimit = float(param[3:])
                except:
                    pass
    # print(path)
    os.chown(path,42103,42103)
    # os.chdir(path)
    # os.chown(target,42103,42103)
    os.chmod(path,0o777)
    # shutil.copyfile(testcase_file_path,f"{path}/{input_filename}")
    os.chroot(path)
    os.chdir("/")
    os.setgid(42103)
    os.setuid(42103)
    # print(os.listdir())
    try:
        # Popen(
        #     target,
        #     stdin=sys.stdin,
        #     stdout=sys.stdout,
        #     stderr=STDOUT
        # )
        if os.path.isfile(input_file_name):
            with open(input_file_name, "rb") as fin, open(output_file_name,"wb") as fout:
                p = Popen(
                    target,
                    stdin=fin,
                    stdout=fout,
                    stderr=STDOUT
                )
        else:
            with open(output_file_name,"wb") as fout:
                p = Popen(
                    target,
                    stdout=fout,
                    stderr=STDOUT
                )

        now = datetime.now()
        deadline = now + timedelta(seconds=timelimit)
        while p.poll() is None:
            if (n:=datetime.now()) > deadline:
                p.kill()
                raise TLEError
        
        if p.poll() != 0:
            raise REError
        # o = check_output(
        #     target,
        #     input=sys.stdin.buffer.read() if not testcase_file_path else None,
        #     stderr=STDOUT,
        #     timeout=timelimit
        # )
    # except CalledProcessError as e:
    except REError:
        # if e.output is None:
        #     e.output = b""
        # sys.stdout.buffer.write(e.output)
        # sys.stderr.write(str(e))
        # exit(e.returncode)
        sys.stderr.write(str(get_error_str(target,p.poll())))
        sys.stderr.flush()
        exit(2)

    # except TimeoutExpired as e:
    except TLEError:
        # if e.output is None:
        #     e.output = b""
        # sys.stdout.buffer.write(e.output)
        # sys.stdout.flush()
        # sys.stderr.write(str(e))
        # sys.stderr.flush()
        # time.sleep(5)
        exit(3)
    # else:
    #     sys.stdout.buffer.write(o)
    exit(0)
    # print(o)