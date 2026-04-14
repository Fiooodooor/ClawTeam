#!/usr/bin/expect -f

set timeout 180

set username [lindex $argv 0];

# Retrieve the password from an environment variable instead of a command-line argument
if {[info exists env(KW_PASSWORD)]} {
    set password $env(KW_PASSWORD)
} else {
    puts stderr "Error: KW_PASSWORD environment variable is not set."
    exit 1
}

# Forward remaining command-line arguments (after the username) to run_kw.sh
set args [lrange $argv 1 end]

spawn ./run_kw.sh {*}$args

expect "Login:"

send "$username\r"

expect "Password:"
send  "$password\r"
expect eof
wait